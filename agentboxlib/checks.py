"""Integration tests touch only the active AgentBox project's resources."""
import json
import subprocess
from . import engine


def agent_probe(state,blocked=False):
    cmd=['exec','-T','--user','0:0','agent','python3','/opt/agentbox/execute.py','python3','/opt/agentbox/probe.py']
    if blocked:cmd+=['--blocked']
    r=engine.compose(state,cmd,capture_output=True,text=True)
    try:return json.loads(r.stdout)
    except (ValueError,TypeError):return {'probe_execution':False}


def integration(state,profile,faults=False):
    report={'normal':agent_probe(state),'faults':'NOT_RUN: use --faults to interrupt this profile','capture':'NOT_RUN: see README capture procedure'}
    if faults:
        report['faults']='EXECUTED: gateway stop and recovery; see phase results'
        engine.compose(state,['stop','gateway'],check=True)
        try:report['gateway_stopped']=agent_probe(state,True)
        finally:
            engine.compose(state,['up','-d','--pull','never','--wait','--wait-timeout','120','gateway'],check=True)
        report['recovered']=agent_probe(state)
    engine.private_write(state/'last-test.json',json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    ok=all(all(section.values()) for section in report.values() if isinstance(section,dict))
    if not ok:return 1
    print('PASS for executed probes; capture and unexecuted fault scenarios remain NOT_RUN')
    return 0
