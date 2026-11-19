"""Generate a closed Compose graph; profiles cannot inject Compose options."""
import hashlib
import ipaddress
from pathlib import Path
from .config import validate


def network_plan(name, existing):
    used=[ipaddress.ip_network(x) for x in existing if ':' not in x]
    seed=int.from_bytes(hashlib.sha256(name.encode()).digest()[:2],'big')%4096
    pool=ipaddress.ip_network('10.224.0.0/12')
    for offset in range(4096):
        start=int(pool.network_address)+((seed+offset)%4096)*256
        networks=[ipaddress.ip_network((start+i*8,29)) for i in range(3)]
        if any(n.overlaps(e) for n in networks for e in used):continue
        a,b,c=networks
        return {'enclave_subnet':str(a),'uplink_subnet':str(b),'ui_subnet':str(c),
                'gateway_ip':str(a[2]),'agent_ip':str(a[3]),'relay_ip':str(a[4]),
                'uplink_ip':str(b[2]),'uplink_gateway':str(b[1])}
    raise ValueError('Нет свободных подсетей AgentBox')


def bind(source,target):
    return {'type':'bind','source':str(Path(source).absolute()),'target':target,'read_only':True,'bind':{'create_host_path':False}}


def render(profile,state,net,identity=None):
    p=validate(profile);state=Path(state).absolute()
    common={'restart':'no','read_only':True,'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],
            'tmpfs':['/tmp:rw,nosuid,nodev,size=512m','/run:rw,nosuid,nodev,noexec,size=32m'],
            'logging':{'driver':'json-file','options':{'max-size':'5m','max-file':'2'}},
            'pids_limit':256,'mem_limit':'512m','cpus':1.0,'init':False,
            'sysctls':{'net.ipv6.conf.all.disable_ipv6':'1','net.ipv6.conf.default.disable_ipv6':'1'}}
    agent={**common,'image':p['agent']['image'],'hostname':'agentbox',
           'entrypoint':['python3','/opt/agentbox/agent.py'],
           'cap_add':['NET_ADMIN','SETUID','SETGID','SETPCAP','CHOWN','DAC_OVERRIDE','FOWNER'],
           'environment':{'HOME':'/home/agent','TZ':'UTC','LANG':'en_US.UTF-8','LC_ALL':'en_US.UTF-8','DISPLAY':':0','BROWSER':'/usr/local/bin/agentbox-browser'},
           'volumes':['home:/home/agent','workspace:/workspace',bind(state/'agent.json','/etc/agentbox.json'),bind(state/'resolv.conf','/etc/resolv.conf'),bind(state/'vnc.password','/secrets/vnc.password')],
           'networks':{'enclave':{'ipv4_address':net['agent_ip']}},'pids_limit':2048,'mem_limit':'3g','cpus':2.0,'shm_size':'512m',
           'healthcheck':{'test':['CMD','python3','/opt/agentbox/ready.py'],'interval':'3s','timeout':'3s','start_period':'5s','retries':10},
           'depends_on':{'gateway':{'condition':'service_healthy'}},'working_dir':'/workspace',
           'security_opt':['no-new-privileges:true',f'seccomp={state / "seccomp.json"}']}
    gateway={**common,'image':'agentbox-gateway:local','entrypoint':['python3','/opt/agentbox/gateway.py'],
             'cap_add':['NET_ADMIN','NET_RAW','SETUID','SETGID','SETPCAP','CHOWN','DAC_OVERRIDE'],
             'volumes':[bind(state/'gateway.json','/etc/agentbox.json'),bind(state/'vpn.conf','/secrets/vpn.conf'),bind(state/'resolv.conf','/etc/resolv.conf')],
             'networks':{'enclave':{'ipv4_address':net['gateway_ip']},'uplink':{'ipv4_address':net['uplink_ip'],'gw_priority':1}},
             'sysctls':{**common['sysctls'],'net.ipv4.ip_forward':'0','net.ipv4.conf.all.rp_filter':'0','net.ipv4.conf.default.rp_filter':'0'},
             'healthcheck':{'test':['CMD','python3','/opt/agentbox/health.py'],'interval':'15s','timeout':'25s','start_period':'20s','retries':2}}
    if p['vpn']['kind']=='openvpn':gateway['devices']=['/dev/net/tun:/dev/net/tun']
    relay={**common,'image':'agentbox-relay:local','entrypoint':['python3','/opt/agentbox/relay.py'],
           'cap_add':['NET_ADMIN','SETUID','SETGID','SETPCAP','DAC_OVERRIDE'],
           'sysctls':{**common['sysctls'],'net.ipv4.ip_forward':'0'},
           'volumes':[bind(state/'relay.json','/etc/agentbox.json')],
           'networks':{'enclave':{'ipv4_address':net['relay_ip']},'ui':{'gw_priority':1}},
           'healthcheck':{'test':['CMD','python3','-c',"import http.client;c=http.client.HTTPConnection('127.0.0.1',6080,timeout=2);c.request('GET','/vnc.html');assert c.getresponse().status==200"],'interval':'3s','timeout':'3s','start_period':'3s','retries':10},
           'ports':[f'127.0.0.1:{p["desktop_port"]}:6080'],'depends_on':{'agent':{'condition':'service_healthy'}}}
    def internal(subnet):
        return {'internal':True,'enable_ipv6':False,'driver_opts':{'com.docker.network.bridge.gateway_mode_ipv4':'isolated'},'ipam':{'config':[{'subnet':subnet}]}}
    return {'name':f'agentbox-{p["name"]}-{hashlib.sha256(str(Path(identity or state).resolve()).encode()).hexdigest()[:10]}','services':{'gateway':gateway,'agent':agent,'relay':relay},
            'networks':{'enclave':internal(net['enclave_subnet']),'uplink':{'enable_ipv6':False,'ipam':{'config':[{'subnet':net['uplink_subnet']}]}},'ui':{'enable_ipv6':False,'ipam':{'config':[{'subnet':net['ui_subnet']}]}}},
            'volumes':{'home':{},'workspace':{}}}
