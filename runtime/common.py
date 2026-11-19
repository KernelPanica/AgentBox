import json
import os
import subprocess
from pathlib import Path


def config():return json.loads(Path('/etc/agentbox.json').read_text())


def run(args,**kw):return subprocess.run(args,check=True,**kw)


def firewall(rules):run(['nft','-f','-'],input=rules,text=True)


def drop_command(args,uid=1000,netraw=False):
    caps='-all,+net_raw' if netraw else '-all'
    return ['setpriv',f'--reuid={uid}',f'--regid={uid}','--clear-groups',f'--bounding-set={caps}',f'--inh-caps={caps}',f'--ambient-caps={caps}','--no-new-privs',*args]


def drop_exec(args,uid=1000,netraw=False):os.execvp('setpriv',drop_command(args,uid,netraw))
