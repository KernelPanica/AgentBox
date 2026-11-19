"""Small local control plane. GUI relay never gets Docker access."""
import argparse
import getpass
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from . import engine
from .config import save,load,validate,validate_vpn
from .transfer import pack,unpack,LIMIT

DEFAULT=engine.ROOT/'.agentbox/profiles/default/profile.json'


def parser():
    p=argparse.ArgumentParser(description='AgentBox — изолированные CLI/GUI агенты через VPN')
    sub=p.add_subparsers(dest='action',required=True)
    for name in ['configure','start','stop','status','shell','doctor','test','render','import','export','password']:
        c=sub.add_parser(name);c.add_argument('--profile',type=Path,default=DEFAULT)
        if name=='configure':
            c.add_argument('--name');c.add_argument('--vpn',choices=['wireguard','openvpn','xray']);c.add_argument('--vpn-config',type=Path)
            c.add_argument('--endpoint',help='literal IPv4:port/tcp или /udp')
            c.add_argument('--image',default='agentbox-agent:local');c.add_argument('--cli',default='bash')
            c.add_argument('--gui',default='agentbox-browser');c.add_argument('--mode',choices=['cli','gui'],default='gui');c.add_argument('--port',type=int,default=6080)
            c.add_argument('--expected-exit-ip')
        if name in ('start','shell'):c.add_argument('command',nargs=argparse.REMAINDER)
        if name=='test':c.add_argument('--faults',action='store_true',help='Прерывает сеть только текущего профиля')
        if name in ('import','export'):c.add_argument('source');c.add_argument('destination')
    b=sub.add_parser('build');b.add_argument('--base-image',help='Альтернативный доверенный Debian-compatible OCI base')
    return p


def configure(a):
    if a.profile.exists():raise ValueError('Профиль существует. Для другой конфигурации задайте новый --profile')
    name=a.name or input('Имя профиля [default]: ').strip() or 'default'
    kind=a.vpn or input('VPN (wireguard/openvpn/xray): ').strip()
    src=a.vpn_config or Path(input('Путь к отдельному VPN-конфигу (не от установленного Claude): ').strip()).expanduser()
    ep=a.endpoint or input('VPN endpoint IPv4:port/tcp или /udp: ').strip()
    try:
        address,proto=ep.rsplit('/',1);ip,port=address.rsplit(':',1)
        endpoints=[{'ip':ip,'port':int(port),'protocol':proto}]
    except ValueError:raise ValueError('Формат endpoint: IPv4:port/tcp или /udp') from None
    p={'name':name,'mode':a.mode,'desktop_port':a.port,'agent':{'image':a.image,'cli':shlex.split(a.cli),'gui':shlex.split(a.gui)},'vpn':{'kind':kind,'config':str(src.absolute()),'endpoints':endpoints}}
    if a.expected_exit_ip:p['expected_exit_ip']=a.expected_exit_ip
    p=validate(p)
    if src.is_symlink() or not src.is_file() or src.stat().st_mode & 0o077:raise ValueError('VPN-файл должен иметь права 0600')
    if (Path.home()/'claude-code').resolve() in src.resolve().parents:raise ValueError('Используйте отдельный VPN config; установленный Claude не импортируется')
    raw=src.read_bytes();validate_vpn(kind,raw,endpoints)
    a.profile.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    copy=a.profile.parent/'vpn.conf'
    if copy.exists():raise ValueError('vpn.conf в каталоге назначения уже существует')
    engine.private_write(copy,raw);p['vpn']['config']=str(copy.absolute());save(a.profile,p)
    print(f'Профиль сохранён: {a.profile.absolute()}\nЗапуск: ./agentbox start --profile {shlex.quote(str(a.profile))}')


def doctor():
    print('Python:',sys.version.split()[0])
    if not shutil.which('docker'):raise ValueError('Docker CLI отсутствует')
    engine.require_engine()
    for args in [['version','--format','{{.Server.Version}}'],['compose','version']]:
        engine.docker(args,check=True)
    print('Docker доступен. Существующие контейнеры и маршруты не изменялись.')


def main(argv=None):
    a=parser().parse_args(argv)
    try:
        if a.action=='configure':configure(a);return 0
        if a.action=='build':engine.require_engine();engine.build(a.base_image);return 0
        if a.action=='doctor':doctor();return 0
        p=load(a.profile);state=a.profile.absolute().parent/'runtime'
        if a.action=='render':
            with engine.lock(state.parent/'operation.lock'):
                if (state/'compose.json').exists():
                    engine.require_engine()
                    if engine.running(state):raise ValueError('Нельзя изменять runtime работающего профиля; сначала stop')
                engine.prepare(p,state,[])
            print(state/'compose.json');return 0
        if a.action=='password':
            if not (state/'vnc.password').exists():raise ValueError('Сначала запустите профиль')
            if not sys.stdout.isatty():raise ValueError('Пароль выводится только в интерактивный терминал')
            print((state/'vnc.password').read_text().strip());return 0
        engine.require_engine()
        if a.action=='status':
            if not (state/'compose.json').exists():print('NOT_STARTED');return 0
            return engine.compose(state,['ps']).returncode
        if a.action=='stop':
            if not (state/'compose.json').exists():return 0
            with engine.lock(state.parent/'operation.lock'):
                result=engine.compose(state,['down','--remove-orphans']).returncode
                if result==0:engine.cleanup_mounts(state)
                return result
        if a.action=='start':
            with engine.lock(state.parent/'operation.lock'):
                if engine.running(state):
                    if (state/'profile.sha256').read_text()!=engine.fingerprint(p):raise ValueError('Профиль изменён: сначала stop')
                    r=engine.compose(state,['ps','-q','agent'],capture_output=True,text=True,check=True)
                    if not r.stdout.strip():raise ValueError('Незавершённый запуск: выполните stop и повторите start')
                else:
                    engine.check_port(p['desktop_port']);engine.ensure_images(p)
                    engine.prepare(p,state,engine.existing_subnets())
                    engine.compose(state,['up','-d','--pull','never','--wait','--wait-timeout','120'],check=True)
            engine.require_healthy(state)
            print(f'Рабочий стол: http://127.0.0.1:{p["desktop_port"]}/vnc.html\nПароль: ./agentbox password --profile {shlex.quote(str(a.profile))}',flush=True)
            command=a.command
            if command and command[0]=='--':command=command[1:]
            if command or p['mode']=='cli':
                with engine.lock(state.parent/'session.lock'):return engine.exec_agent(state,command or p['agent']['cli'])
            return 0
        if not engine.running(state):raise ValueError('Профиль не запущен')
        if a.action in ('shell','import','export'):engine.require_healthy(state)
        if a.action=='shell':
            cmd=a.command
            if cmd and cmd[0]=='--':cmd=cmd[1:]
            with engine.lock(state.parent/'session.lock'):return engine.exec_agent(state,cmd or ['bash'])
        if a.action=='test':
            from .checks import integration
            return integration(state,p,a.faults)
        if a.action=='import':
            dest=a.destination
            if not dest.startswith('/workspace/') or '..' in Path(dest).parts:raise ValueError('Назначение — каталог внутри /workspace/')
            data=pack(Path(a.source).expanduser())
            # Container-side extractor has same validation; agent UID has no host access.
            return engine.compose(state,['exec','-T','--user','0:0','agent','python3','/opt/agentbox/execute.py','python3','/opt/agentbox/exchange.py','import',dest],input=data).returncode
        if a.action=='export':
            if not a.source.startswith('/workspace/') or '..' in Path(a.source).parts:raise ValueError('Источник — файл/каталог внутри /workspace/')
            import tempfile
            with tempfile.TemporaryFile() as output:
                r=engine.compose(state,['exec','-T','--user','0:0','agent','python3','/opt/agentbox/execute.py','python3','/opt/agentbox/exchange.py','export',a.source],stdout=output)
                if r.returncode:raise ValueError('Экспорт из контейнера не выполнен')
                output.seek(0);data=output.read(LIMIT+1)
            unpack(data,Path(a.destination).expanduser());return 0
    except (ValueError,OSError,subprocess.CalledProcessError,json.JSONDecodeError,KeyError) as e:
        # Never echo external commands/config contents/credentials in errors.
        if isinstance(e,subprocess.CalledProcessError):message='Команда Docker завершилась ошибкой; прямой fallback запрещён'
        elif isinstance(e,OSError):message=f'Ошибка доступа к файлу/программе: {e.strerror}'
        else:message=str(e)
        print('AgentBox:',message,file=sys.stderr);return 1
    except KeyboardInterrupt:return 130
    return 0
