"""Local lifecycle operations, scoped to one generated Compose project."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import string
import subprocess
import tempfile
from pathlib import Path
from .config import validate, validate_vpn
from .compose import render,network_plan

ROOT=Path(__file__).resolve().parents[1]


def private_write(path,data):
    path=Path(path)
    if path.is_symlink():raise ValueError('Симлинк в runtime')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    os.fchmod(fd,0o600)
    with os.fdopen(fd,'wb') as f:f.write(data.encode() if isinstance(data,str) else data)


@contextmanager
def lock(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Для профиля уже выполняется операция/CLI-сессия') from None
        yield
    finally:os.close(fd)


def fingerprint(p):return hashlib.sha256(json.dumps(validate(p),sort_keys=True).encode()).hexdigest()


def prepare(profile,state,existing):
    p=validate(profile);state=Path(state).absolute()
    if state.is_symlink() or any(x.is_symlink() for x in state.parents):raise ValueError('Симлинк в runtime path')
    source=Path(p['vpn']['config']).absolute()
    if source.is_symlink() or not source.is_file() or source.stat().st_mode & 0o077:raise ValueError('VPN config должен быть обычным приватным файлом 0600')
    raw=source.read_bytes();validate_vpn(p['vpn']['kind'],raw,p['vpn']['endpoints'])
    state.mkdir(parents=True,exist_ok=True,mode=0o700);state.chmod(0o700)
    if (state/'network.json').exists():net=json.loads((state/'network.json').read_text())
    else:net=network_plan(p['name'],existing)
    for name,content in {
        'network.json':net,
        'agent.json':{k:net[k] for k in ['agent_ip','gateway_ip','relay_ip']}|{'mode':p['mode'],'gui':p['agent']['gui']},
        'relay.json':{'agent_ip':net['agent_ip']},
        'gateway.json':net|{'kind':p['vpn']['kind'],'endpoints':p['vpn']['endpoints'],'expected_exit_ip':p.get('expected_exit_ip','')}
    }.items():private_write(state/name,json.dumps(content,indent=2))
    private_write(state/'vpn.conf',raw)
    private_write(state/'resolv.conf',f'nameserver {p["dns"]}\noptions timeout:2 attempts:2\n')
    if not (state/'vnc.password').exists():private_write(state/'vnc.password',''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(8))+'\n')
    private_write(state/'seccomp.json',(ROOT/'runtime/seccomp.json').read_bytes())
    mount_dir=stage_mounts(state)
    private_write(state/'compose.json',json.dumps(render(p,mount_dir,net,identity=state),indent=2))
    private_write(state/'profile.sha256',fingerprint(p))
    return state


def docker(args,**kwargs):
    # No shell or Compose ambient overrides; Docker credentials remain on host.
    env={k:v for k,v in os.environ.items() if not k.startswith('COMPOSE_')}
    return subprocess.run(['docker',*args],env=env,**kwargs)


def require_engine():
    context=os.environ.get('DOCKER_CONTEXT')
    endpoint=os.environ.get('DOCKER_HOST') if not context else None
    if endpoint and not endpoint.startswith('unix:///'):raise ValueError('Поддерживается только локальный Docker через Unix socket')
    if not endpoint:
        args=['context','inspect']+([context] if context else [])+['--format','{{.Endpoints.docker.Host}}']
        r=docker(args,capture_output=True,text=True)
        if r.returncode or not r.stdout.strip().startswith('unix:///'):raise ValueError('Поддерживается только локальный Docker через Unix socket')
    r=docker(['info','--format','{{.OSType}}'],capture_output=True,text=True)
    if r.returncode or r.stdout.strip()!='linux':raise ValueError('Нужен доступ к локальному Docker Engine (Linux); выполните ./agentbox doctor')
    for args,floor in [(['version','--format','{{.Server.Version}}'],(28,0,0)),(['compose','version','--short'],(2,33,1))]:
        r=docker(args,capture_output=True,text=True)
        parts=tuple(int(x) for x in re.findall(r'\d+',r.stdout)[:3]);parts=parts+(0,)*(3-len(parts))
        if r.returncode or parts<floor:raise ValueError('Требуются Docker Engine 28+ и Compose 2.33.1+')


def compose(state,args,**kwargs):
    state=Path(state).absolute()
    name=json.loads((state/'compose.json').read_text())['name']
    if not name.startswith('agentbox-'):raise ValueError('Чужой Compose project')
    return docker(['compose','--project-directory',str(state),'-p',name,'-f',str(state/'compose.json'),*args],**kwargs)


def existing_subnets():
    r=docker(['network','ls','-q'],capture_output=True,text=True,check=True)
    ids=r.stdout.split()
    if not ids:return []
    r=docker(['network','inspect',*ids],capture_output=True,text=True,check=True)
    return [c['Subnet'] for n in json.loads(r.stdout) for c in (n.get('IPAM',{}).get('Config') or []) if c.get('Subnet')]


def running(state):
    if not (Path(state)/'compose.json').exists():return False
    r=compose(state,['ps','--status','running','-q'],capture_output=True,text=True,check=True)
    return bool(r.stdout.strip())


def check_port(port):
    with socket.socket() as s:
        try:s.bind(('127.0.0.1',port))
        except OSError:raise ValueError(f'Порт {port} занят; выберите другой desktop_port') from None


def build(base=None):
    for name in ['gateway','agent','relay']:
        args=['build','-t',f'agentbox-{name}:local','-f',str(ROOT/'images'/f'{name}.Dockerfile')]
        if base:args+=['--build-arg',f'BASE_IMAGE={base}']
        docker([*args,str(ROOT)],check=True)


def ensure_images(profile):
    required=['agentbox-gateway:local','agentbox-relay:local',profile['agent']['image']]
    missing=[image for image in required if docker(['image','inspect',image],capture_output=True).returncode]
    if any(x not in ['agentbox-gateway:local','agentbox-relay:local','agentbox-agent:local'] for x in missing):
        raise ValueError('Сначала соберите указанный собственный образ агента')
    if missing:build()


def exec_agent(state,command,interactive=True):
    args=['exec','--user','0:0','-e','HOME=/home/agent','-e','DISPLAY=:0','-e','BROWSER=/usr/local/bin/agentbox-browser']
    if not interactive or not os.isatty(0):args+=['-T']
    # docker compose exec owns TTY and forwards signals directly.
    return compose(state,[*args,'agent','python3','/opt/agentbox/execute.py',*command]).returncode


def require_healthy(state):
    for service in ['gateway','agent','relay']:
        r=compose(state,['ps','--status','running','-q',service],capture_output=True,text=True,check=True)
        cid=r.stdout.strip()
        if not cid:raise ValueError(f'{service} не запущен; выполните stop и start')
        r=docker(['inspect','--format','{{.State.Health.Status}}',cid],capture_output=True,text=True,check=True)
        if r.stdout.strip()!='healthy':raise ValueError(f'{service} не готов; команды агента не запускаются')


def mount_prefix(state):
    tag=hashlib.sha256(str(Path(state).resolve()).encode()).hexdigest()[:10]
    return f'agentbox-runtime-{tag}-'


def valid_mount_dir(path,state):
    path=Path(path)
    return (path.parent==Path('/tmp') and path.name.startswith(mount_prefix(state))
            and not path.is_symlink() and path.is_dir()
            and path.stat().st_uid==os.getuid() and path.stat().st_mode & 0o077==0)


def stage_mounts(state):
    # Bind-mount roots appear in /proc/mountinfo. Never expose host username/path.
    marker=state/'mount-dir'
    directory=Path(marker.read_text()) if marker.exists() else None
    if directory is None or not valid_mount_dir(directory,state):
        directory=Path(tempfile.mkdtemp(prefix=mount_prefix(state),dir='/tmp'))
        private_write(marker,str(directory))
    for name in ['agent.json','gateway.json','relay.json','resolv.conf','vpn.conf','vnc.password','seccomp.json']:
        private_write(directory/name,(state/name).read_bytes())
    return directory


def cleanup_mounts(state):
    state=Path(state);marker=state/'mount-dir'
    if not marker.exists():return
    directory=Path(marker.read_text())
    if not valid_mount_dir(directory,state):raise ValueError('Недопустимый runtime staging path; очистка отклонена')
    shutil.rmtree(directory);marker.unlink()
