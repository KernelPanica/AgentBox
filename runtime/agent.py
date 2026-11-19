"""Trusted one-shot setup; no application starts before rules and privilege drop."""
import os
import subprocess
from pathlib import Path
from common import config,run,firewall,drop_exec
from policy import agent_rules

c=config();firewall(agent_rules(c))
run(["ip","route","replace","default","via",c["gateway_ip"],"dev","eth0"])
for name in ['/home/agent','/workspace','/run/agent','/run/user/1000']:
    path=Path(name);path.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chown(path,1000,1000);os.chmod(path,0o700)
password=Path('/secrets/vnc.password').read_bytes().strip()
vnc=subprocess.check_output(['tigervncpasswd','-f'],input=password+b'\n')
path=Path('/run/agent/vnc.passwd');path.write_bytes(vnc);os.chmod(path,0o600);os.chown(path,1000,1000)
os.environ['XDG_RUNTIME_DIR']='/run/user/1000'
drop_exec(['tini','--','python3','/opt/agentbox/session.py'])
