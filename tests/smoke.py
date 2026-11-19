#!/usr/bin/env python3
"""Real offline smoke test. No VPN credentials; only agentbox-smoke resources."""
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agentboxlib import engine
from agentboxlib.config import save

ROOT=engine.ROOT;STATE=ROOT/'.agentbox/smoke/runtime'

def setup():
    folder=STATE.parent;folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    vpn=folder/'fixture.json'
    data={'outbounds':[{'protocol':'vless','settings':{'vnext':[{'address':'1.1.1.1','port':9,'users':[{'id':'00000000-0000-4000-8000-000000000001','encryption':'none'}]}]},'streamSettings':{'network':'tcp','security':'tls','tlsSettings':{'serverName':'example.com'}}}]}
    engine.private_write(vpn,json.dumps(data))
    p={'name':'smoke','mode':'gui','desktop_port':16080,'agent':{'image':'agentbox-agent:local','cli':['bash'],'gui':['agentbox-browser','about:blank']},'vpn':{'kind':'xray','config':str(vpn),'endpoints':[{'ip':'1.1.1.1','port':9,'protocol':'tcp'}]}}
    if not (folder/'profile.json').exists():save(folder/'profile.json',p)
    engine.prepare(p,STATE,engine.existing_subnets())
    return p


def run():
    setup()
    engine.compose(STATE,['config','-q'],check=True)
    engine.compose(STATE,['up','-d','--no-deps','--pull','never','agent','relay'],check=True)
    time.sleep(4)
    r=engine.compose(STATE,['exec','-T','--user','0:0','agent','python3','/opt/agentbox/execute.py','python3','/opt/agentbox/probe.py','--blocked'],capture_output=True,text=True)
    print(r.stdout);print(r.stderr,file=sys.stderr)
    engine.private_write(ROOT/'reports/smoke.json',r.stdout)
    if r.returncode:raise SystemExit(r.returncode)
    # Browser sandbox must work for custom agent GUI/login flows.
    r=engine.compose(STATE,['exec','-T','--user','0:0','agent','python3','/opt/agentbox/execute.py','timeout','20','chromium','--headless','--disable-gpu','--disable-dev-shm-usage','--screenshot=/tmp/browser-smoke.png','about:blank'],capture_output=True,text=True)
    print('Chromium sandbox smoke exit:',r.returncode)
    if r.returncode:print(r.stderr[-3000:]);raise SystemExit(r.returncode)
    print('Offline desktop: http://127.0.0.1:16080/vnc.html; test resources left for UI inspection. Cleanup: python3 tests/smoke.py down')

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='down':
        result=engine.compose(STATE,['down','--volumes']).returncode
        if result==0:engine.cleanup_mounts(STATE)
        raise SystemExit(result)
    run()
