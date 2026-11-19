#!/usr/bin/env python3
"""Local two-peer WireGuard dataplane test; no real provider or internet exit."""
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agentboxlib import engine

STATE=engine.ROOT/'.agentbox/wg-fixture/runtime'
SERVER='agentbox-wg-fixture-peer'


def keypair():
    private=base64.b64encode(os.urandom(32)).decode()
    r=engine.docker(['run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--entrypoint','wg','agentbox-gateway:local','pubkey'],input=private+'\n',capture_output=True,text=True,check=True)
    return private,r.stdout.strip()


def main():
    created=False;prepared=False
    if engine.docker(['container','inspect',SERVER],capture_output=True).returncode==0:raise SystemExit('Fixture peer already exists; refuse to touch it')
    client_private,client_public=keypair();server_private,server_public=keypair()
    STATE.parent.mkdir(parents=True,exist_ok=True,mode=0o700);STATE.mkdir(exist_ok=True,mode=0o700)
    existing=engine.existing_subnets()
    import ipaddress
    # A public-shaped endpoint exists only in our disposable local Docker subnet.
    # Check it does not overlap any existing Docker network before creating it.
    fixture_subnet='11.254.253.0/29'
    if any(ipaddress.ip_network(fixture_subnet).overlaps(ipaddress.ip_network(x)) for x in existing if ':' not in x):raise SystemExit('Fixture subnet in use; refusing')
    net=engine.network_plan('wg-fixture',existing)
    net.update(uplink_subnet=fixture_subnet,uplink_ip='11.254.253.2',uplink_gateway='11.254.253.1')
    engine.private_write(STATE/'network.json',json.dumps(net))
    cfg=STATE.parent/'wg.conf'
    engine.private_write(cfg,f'[Interface]\nPrivateKey = {client_private}\nAddress = 10.8.0.2/32\n[Peer]\nPublicKey = {server_public}\nAllowedIPs = 0.0.0.0/0\nEndpoint = 11.254.253.3:51820\nPersistentKeepalive = 1\n')
    p={'name':'wg-fixture','agent':{'image':'agentbox-agent:local','cli':['bash'],'gui':['agentbox-browser','about:blank']},'mode':'gui','desktop_port':16081,'vpn':{'kind':'wireguard','config':str(cfg),'endpoints':[{'ip':'11.254.253.3','port':51820,'protocol':'udp'}]}}
    engine.prepare(p,STATE,existing);prepared=True
    project=json.loads((STATE/'compose.json').read_text())['name']
    try:
        engine.compose(STATE,['up','-d','--no-deps','--pull','never','gateway'],check=True)
        engine.docker(['run','-d','--name',SERVER,'--network',project+'_uplink','--ip','11.254.253.3','--read-only','--cap-drop','ALL','--cap-add','NET_ADMIN','--tmpfs','/run','--tmpfs','/tmp','--entrypoint','sleep','agentbox-gateway:local','infinity'],stdout=subprocess.DEVNULL,check=True);created=True
        script=f'''import subprocess
from pathlib import Path
r=lambda a,**kw:subprocess.run(a,check=True,**kw)
r(['ip','link','add','vpn0','type','wireguard'])
r(['wg','setconf','vpn0','/dev/stdin'],input={f'[Interface]{chr(10)}PrivateKey = {server_private}{chr(10)}ListenPort = 51820{chr(10)}[Peer]{chr(10)}PublicKey = {client_public}{chr(10)}AllowedIPs = 10.8.0.2/32{chr(10)}'!r},text=True)
r(['ip','addr','add','10.8.0.1/24','dev','vpn0'])
r(['ip','route','replace','11.254.253.2/32','via','11.254.253.1','dev','eth0'])
r(['ip','addr','add','1.1.1.1/32','dev','lo'])
r(['ip','link','set','vpn0','up'])
'''
        engine.docker(['exec','-i',SERVER,'python3','-'],input=script,text=True,check=True)
        code="import socket; s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('1.1.1.1',8443));s.listen();\nwhile True:\n c,a=s.accept();c.sendall(b'agentbox-local-wireguard-fixture');c.close()"
        engine.docker(['exec','-d','--user','900:900',SERVER,'python3','-c',code],check=True)
        engine.compose(STATE,['up','-d','--no-deps','--pull','never','agent'],check=True)
        time.sleep(4)
        code="import socket; s=socket.create_connection(('1.1.1.1',8443),timeout=5);assert s.recv(128)==b'agentbox-local-wireguard-fixture';print('local WireGuard round trip PASS')"
        engine.compose(STATE,['exec','-T','--user','0:0','agent','python3','/opt/agentbox/execute.py','python3','-c',code],check=True)
        inspect=f"from pathlib import Path;import json,subprocess;route=lambda a:json.loads(subprocess.check_output(a,text=True))[0]['dev'];inside=route(['ip','-j','route','get','{net['agent_ip']}']);outside=route(['ip','-j','route','get','11.254.253.3']);print(json.dumps({{'global':Path('/proc/sys/net/ipv4/ip_forward').read_text().strip(),'inside':Path('/proc/sys/net/ipv4/conf/'+inside+'/forwarding').read_text().strip(),'outside':Path('/proc/sys/net/ipv4/conf/'+outside+'/forwarding').read_text().strip(),'tunnel':Path('/proc/sys/net/ipv4/conf/tun0/forwarding').read_text().strip()}}))"
        r=engine.compose(STATE,['exec','-T','--user','0:0','gateway','python3','-c',inspect],capture_output=True,text=True,check=True)
        settings=json.loads(r.stdout);assert settings=={'global':'0','inside':'1','outside':'0','tunnel':'1'},settings
        engine.compose(STATE,['stop','gateway'],check=True)
        r=engine.compose(STATE,['exec','-T','--user','0:0','agent','python3','/opt/agentbox/execute.py','python3','-c',code],capture_output=True,text=True)
        assert r.returncode!=0
        report={'local_wireguard_roundtrip':'PASS','forwarding':settings,'gateway_stopped_blocks_tunnel':'PASS','remote_vpn_exit':'NOT_RUN'}
        engine.private_write(engine.ROOT/'reports/wireguard-fixture.json',json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:
        if sys.exc_info()[0] is not None and prepared:engine.compose(STATE,['logs','--tail','15','gateway'])
        if created:engine.docker(['rm','-f',SERVER],stdout=subprocess.DEVNULL,check=True)
        if prepared:
            engine.compose(STATE,['down','--volumes'],check=True)
            engine.cleanup_mounts(STATE)

if __name__=='__main__':main()
