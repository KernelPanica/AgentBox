#!/usr/bin/env python3
import ipaddress
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from common import config,run,firewall,drop_exec,drop_command
from policy import gateway_rules
from forwarding import set_forwarding
from agentboxlib.config import wireguard_config,openvpn_config,xray_config

c=config()
routes=json.loads(subprocess.check_output(['ip','-j','route','show','default'],text=True))
if len(routes)!=1:raise SystemExit('Expected one uplink default route')
route=routes[0];iface=route['dev'];gateway=route['gateway']
if not re.fullmatch(r'eth[0-9]+',iface) or gateway!=c['uplink_gateway']:raise SystemExit('Unexpected uplink interface')
firewall(gateway_rules(c,iface,gateway))
if c['kind']!='xray':
    inside=json.loads(subprocess.check_output(['ip','-j','route','get',c['agent_ip']],text=True))[0]['dev']
    if not re.fullmatch(r'eth[0-9]+',inside) or inside==iface:raise SystemExit('Unexpected enclave interface')
    set_forwarding(inside)
# Route VPN server through uplink even after full-tunnel default is installed.
for e in c['endpoints']:run(['ip','route','replace',e['ip']+'/32','via',gateway,'dev',iface])
raw=Path('/secrets/vpn.conf').read_bytes()
private=Path('/run/vpn');private.mkdir(mode=0o700);os.chown(private,900,900)

def private_file(name,data):
    p=private/name;p.write_text(data);p.chmod(0o600);os.chown(p,900,900);return str(p)

if c['kind']=='wireguard':
    text,addresses,mtu=wireguard_config(raw,c['endpoints'])
    path=private_file('wg.conf',text)
    run(['ip','link','add','tun0','type','wireguard'])
    run(['wg','setconf','tun0',path])
    for addr in addresses:run(['ip','address','add',addr,'dev','tun0'])
    run(['ip','link','set','tun0','mtu',str(mtu),'up'])
    set_forwarding('tun0')
    run(['ip','route','replace','default','dev','tun0'])
    drop_exec(['tini','--','sleep','infinity'],900)
elif c['kind']=='xray':
    text=json.dumps(xray_config(raw,c['endpoints']))
    path=private_file('xray.json',text)
    run(['ip','rule','add','fwmark','1','lookup','100','priority','100'])
    run(['ip','route','replace','local','0.0.0.0/0','dev','lo','table','100'])
    drop_exec(['tini','--','xray','run','-config',path],900,netraw=True)
else:
    # OpenVPN drops its own UID after tun setup; trusted route supervisor retains NET_ADMIN.
    text=openvpn_config(raw,c['endpoints'])+'\nuser vpn\ngroup vpn\npersist-key\npersist-tun\n'
    path=private_file('openvpn.conf',text)
    child=subprocess.Popen(['openvpn','--config',path])
    def stop(sig,frame):
        child.terminate()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    while child.poll() is None:
        if Path('/sys/class/net/tun0').exists():
            set_forwarding('tun0')
            subprocess.run(['ip','route','replace','default','dev','tun0'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        time.sleep(.5)
    raise SystemExit(child.returncode)
