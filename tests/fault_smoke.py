#!/usr/bin/env python3
"""Offline failure probes, scoped to the disposable smoke profile. No real VPN."""
import json
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agentboxlib import engine
from smoke import STATE,setup


def probe():
    r=engine.compose(STATE,['exec','-T','--user','0:0','agent','python3','/opt/agentbox/execute.py','python3','/opt/agentbox/probe.py','--blocked'],capture_output=True,text=True)
    if r.returncode:print(r.stdout,r.stderr,flush=True);raise RuntimeError('Blocked network probe failed')
    result=json.loads(r.stdout);assert all(result.values()),result
    return result


def main():
    setup();report={}
    try:
        engine.compose(STATE,['up','-d','--no-deps','--pull','never','agent','relay'],check=True)
        time.sleep(4);report['agent_before_gateway']=probe();print('PASS agent before gateway',flush=True)
        engine.compose(STATE,['up','-d','--no-deps','--pull','never','gateway'],check=True)
        time.sleep(2)
        engine.compose(STATE,['exec','-T','--user','0:0','gateway','nft','list','table','netdev','agentbox_wire'],stdout=subprocess.DEVNULL,check=True)
        report['unusable_vpn']=probe();print('PASS unusable VPN',flush=True)
        refused=subprocess.run([sys.executable,str(engine.ROOT/'agentbox'),'start','--profile',str(STATE.parent/'profile.json')],capture_output=True,text=True)
        assert refused.returncode==1
        report['cli_refuses_unhealthy_gateway']=True
        rules='table inet agentbox_fault {\n chain output {\n type filter hook output priority -300; policy drop;\n }\n}\n'
        engine.compose(STATE,['exec','-T','--user','0:0','gateway','nft','-f','-'],input=rules,text=True,check=True)
        report['endpoint_blackout']=probe();print('PASS endpoint blackout',flush=True)
        engine.compose(STATE,['exec','-T','--user','0:0','gateway','nft','delete','table','inet','agentbox_fault'],check=True)
        # Watch literal-IP connects continuously while gateway namespace is replaced.
        code='''import socket,time,json,sys
sys.path.insert(0,'/opt/agentbox')
from probe import tls_exchange
leaks=0;attempts=0;end=time.monotonic()+8
while time.monotonic()<end:
 try:
  if tls_exchange('1.1.1.1',443):leaks+=1
 except OSError:pass
 attempts+=1
print(json.dumps({'leaks':leaks,'attempts':attempts}))
raise SystemExit(1 if leaks else 0)
'''
        import tempfile
        with tempfile.TemporaryFile() as output:
            command=['exec','-T','--user','0:0','agent','python3','/opt/agentbox/execute.py','python3','-c',code]
            # This test process runs alongside a separate lifecycle operation by design.
            name=json.loads((STATE/'compose.json').read_text())['name']
            watcher=subprocess.Popen(['docker','compose','-p',name,'-f',str(STATE/'compose.json'),*command],stdout=output)
            time.sleep(.3)
            engine.compose(STATE,['up','-d','--force-recreate','--no-deps','--pull','never','gateway'],check=True)
            assert watcher.wait(timeout=15)==0
            output.seek(0);report['gateway_recreated']=json.loads(output.read())
        print('PASS gateway recreated',flush=True)
        cid=engine.compose(STATE,['ps','-q','gateway'],capture_output=True,text=True,check=True).stdout.strip()
        engine.docker(['kill','--signal','KILL',cid],stdout=subprocess.DEVNULL,check=True)
        report['gateway_killed']=probe();print('PASS gateway killed',flush=True)
        # Persistence across the supported full stop/start, without real VPN dependency in fixture.
        engine.compose(STATE,['exec','-T','--user','0:0','agent','python3','/opt/agentbox/execute.py','python3','-c',"from pathlib import Path;Path('/workspace/smoke-marker').write_text('preserved')"],check=True)
        engine.compose(STATE,['down'],check=True)
        engine.compose(STATE,['up','-d','--no-deps','--pull','never','agent','relay'],check=True)
        time.sleep(4)
        r=engine.compose(STATE,['exec','-T','--user','0:0','agent','python3','/opt/agentbox/execute.py','cat','/workspace/smoke-marker'],capture_output=True,text=True,check=True)
        report['volume_preserved']=r.stdout=='preserved';assert report['volume_preserved']
        print('PASS volume persistence',flush=True)
        engine.private_write(engine.ROOT/'reports/fault-smoke.json',json.dumps(report,indent=2))
    finally:
        engine.compose(STATE,['down','--volumes'],check=True)
        engine.cleanup_mounts(STATE)

if __name__=='__main__':main()
