#!/usr/bin/env python3
"""Read-only header capture on exactly one AgentBox bridge, no payload persisted."""
import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agentboxlib import engine


def capture(state,seconds):
    document=json.loads((state/'compose.json').read_text());project=document['name']
    if not project.startswith('agentbox-'):raise ValueError('Not an AgentBox project')
    c=json.loads((state/'gateway.json').read_text())
    inspected=engine.docker(['network','inspect',project+'_uplink'],capture_output=True,text=True,check=True)
    net=json.loads(inspected.stdout)[0]
    bridge=net.get('Options',{}).get('com.docker.network.bridge.name') or 'br-'+net['Id'][:12]
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,15}',bridge):raise ValueError('Invalid bridge interface')
    gateway=engine.compose(state,['ps','-q','gateway'],capture_output=True,text=True,check=True).stdout.strip()
    container=json.loads(engine.docker(['inspect',gateway],capture_output=True,text=True,check=True).stdout)[0]
    mac=container['NetworkSettings']['Networks'][project+'_uplink']['MacAddress']
    if not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',mac):raise ValueError('Invalid gateway MAC')
    allowed={(x['ip'],x['port'],x['protocol']) for x in c['endpoints']}
    # --network host is ONLY for this temporary trusted diagnostic observer.
    # It has no NET_ADMIN, mounts, Docker socket, ports or application data.
    observer='agentbox-uplink-observer-'+str(os.getpid())
    args=['run','--rm','--name',observer,'--network','host','--read-only','--cap-drop','ALL','--cap-add','NET_RAW','--security-opt','no-new-privileges:true','agentbox-inspector:local',
          '-Z','root','-p','-n','-q','-l','--immediate-mode','-tt','-s','54','-i',bridge,'ether src '+mac+' and not arp']
    with tempfile.TemporaryFile(mode='w+') as output,tempfile.TemporaryFile(mode='w+') as errors:
        process=subprocess.Popen(['docker',*args],stdout=output,stderr=errors,text=True)
        try:
            ready_deadline=time.monotonic()+15
            while True:
                errors.seek(0);message=errors.read()
                if 'listening on ' in message:break
                if process.poll() is not None or time.monotonic()>ready_deadline:
                    raise RuntimeError('Capture did not become ready')
                time.sleep(.1)
            print('CAPTURE_STARTED',flush=True)
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                if process.poll() is not None:
                    errors.seek(0);raise RuntimeError('Capture process exited early: '+errors.read()[-1500:])
                time.sleep(.25)
        finally:
            try:
                if process.poll() is None:
                    process.send_signal(__import__('signal').SIGINT)
                    try:process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        try:process.wait(timeout=5)
                        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            finally:
                engine.docker(['rm','-f',observer],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        output.seek(0);lines=output.read().splitlines()
    report=summarize_capture(lines,allowed,seconds)
    engine.private_write(engine.ROOT/'reports/xray-uplink-capture.json',json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    return 0 if report['status']=='PASS' else 1


def summarize_capture(lines,allowed,seconds):
    observed=good=violations=unparsed=0
    for line in lines:
        if not line.strip():continue
        match=re.search(r'\bIP ([0-9.]+) > ([0-9.]+):\s*(.*)$',line)
        if not match:unparsed+=1;continue
        origin,destination,description=match.groups()
        # Header notation appends .port to literal IPv4 for TCP/UDP.
        observed+=1
        proto='tcp' if description.startswith('tcp') or 'Flags [' in description else 'udp' if description.startswith('UDP') else 'other'
        try:ip,port=destination.rsplit('.',1);port=int(port);ip=str(ipaddress.IPv4Address(ip))
        except (ValueError,TypeError):violations+=1;continue
        if (ip,port,proto) in allowed:good+=1
        else:violations+=1
    report={'scope':'Gateway Ethernet egress on dedicated uplink bridge, all IP sources; ARP excluded; packet summaries only','duration_seconds':seconds,'observed_packets':observed,'endpoint_transport_packets':good,'violating_packets':violations,'unparsed_lines':unparsed,
            'physical_interface':'NOT_RUN','status':'PASS' if observed>0 and violations==0 and unparsed==0 else 'FAIL'}
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True);p.add_argument('--seconds',type=int,default=45);a=p.parse_args()
    if not 5<=a.seconds<=120:raise SystemExit('Duration must be 5..120 seconds')
    raise SystemExit(capture(a.profile.absolute().parent/'runtime',a.seconds))
