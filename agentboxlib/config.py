"""Strict, deliberately small configuration surface. Never execute VPN config hooks."""
import ipaddress
import json
import os
import re
import shlex
from pathlib import Path


def keys(obj, allowed, required=()):
    if not isinstance(obj, dict) or set(obj)-set(allowed) or set(required)-set(obj):
        raise ValueError('Недопустимые или отсутствующие поля конфигурации')


def public4(value):
    ip=ipaddress.IPv4Address(value)
    if not ip.is_global or ip.is_multicast or str(ip)!=value:
        raise ValueError('Нужен публичный literal IPv4')
    return str(ip)


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'Ожидается целое число {low}..{high}')
    return value


def command(value):
    if not isinstance(value,list) or not value or not all(isinstance(x,str) and x and '\x00' not in x and len(x)<8192 for x in value):
        raise ValueError('Команда должна быть непустым массивом строк')
    if any(x=='--no-sandbox' for x in value):
        raise ValueError('Отключение browser sandbox запрещено')
    return value


def validate(data):
    keys(data, {'name','agent','vpn','mode','dns','desktop_port','expected_exit_ip'}, {'name','agent','vpn'})
    p=json.loads(json.dumps(data))
    if not isinstance(p['name'],str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,31}',p['name']) or p['name'].startswith('claude'):
        raise ValueError('Имя профиля: a-z, 0-9, дефис; префикс claude зарезервирован')
    a=p['agent'];keys(a,{'image','cli','gui'},{'image','cli'})
    if not isinstance(a['image'],str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._/:@-]{0,240}',a['image']):
        raise ValueError('Некорректное имя OCI image')
    command(a['cli']);command(a.get('gui',['chromium','--ozone-platform=x11']))
    a.setdefault('gui',['chromium','--ozone-platform=x11'])
    p.setdefault('mode','cli')
    if p['mode'] not in ('cli','gui'):raise ValueError('mode: cli или gui')
    p['dns']=public4(p.get('dns','1.1.1.1'))
    p['desktop_port']=integer(p.get('desktop_port',6080),1024,65535)
    if p.get('expected_exit_ip'):p['expected_exit_ip']=public4(p['expected_exit_ip'])
    v=p['vpn'];keys(v,{'kind','config','endpoints'},{'kind','config','endpoints'})
    if v['kind'] not in ('wireguard','openvpn','xray'):raise ValueError('Неизвестный VPN adapter')
    if not isinstance(v['config'],str) or not v['config'] or '\x00' in v['config']:raise ValueError('Нужен путь VPN config')
    if not isinstance(v['endpoints'],list) or not 1<=len(v['endpoints'])<=8:raise ValueError('Нужны 1..8 endpoint')
    for ep in v['endpoints']:
        keys(ep,{'ip','port','protocol'},{'ip','port','protocol'})
        ep['ip']=public4(ep['ip']);integer(ep['port'],1,65535)
        if ep['protocol'] not in ('tcp','udp'):raise ValueError('protocol: tcp или udp')
        if v['kind']=='wireguard' and ep['protocol']!='udp':raise ValueError('WireGuard требует UDP')
        if v['kind']=='xray' and ep['protocol']!='tcp':raise ValueError('Xray adapter поддерживает TCP transport')
    return p


def endpoint_allowed(ip,port,proto,endpoints):
    if not any(e['ip']==ip and e['port']==int(port) and e['protocol']==proto for e in endpoints):
        raise ValueError('VPN endpoint не совпадает с allowlist')


def wireguard_config(raw,endpoints):
    section=None; lines=[];addresses=[];mtu=1420;peers=0
    for line in raw.decode().splitlines():
        line=line.split('#',1)[0].strip()
        if not line:continue
        if line in ('[Interface]','[Peer]'):
            section=line;lines.append(line)
            if line=='[Peer]':peers+=1
            continue
        if section is None or '=' not in line:raise ValueError('Некорректный WireGuard config')
        key,value=map(str.strip,line.split('=',1))
        allowed={'PrivateKey','ListenPort','Address','MTU'} if section=='[Interface]' else {'PublicKey','PresharedKey','AllowedIPs','Endpoint','PersistentKeepalive'}
        if key not in allowed:raise ValueError('WireGuard hooks/DNS/includes запрещены')
        if key=='Address':
            for addr in value.split(','):
                addresses.append(str(ipaddress.IPv4Interface(addr.strip())))
            continue
        if key=='MTU':mtu=integer(int(value),576,1500);continue
        if key=='Endpoint':
            ip,port=value.rsplit(':',1);endpoint_allowed(public4(ip),int(port),'udp',endpoints)
        if key=='AllowedIPs':
            if value!='0.0.0.0/0':raise ValueError('WireGuard требует AllowedIPs = 0.0.0.0/0')
        lines.append(f'{key} = {value}')
    if not addresses or peers!=1 or sum(x.startswith('Endpoint = ') for x in lines)!=1 or not any(x=='AllowedIPs = 0.0.0.0/0' for x in lines):
        raise ValueError('Нужны Interface Address и один full-tunnel Peer с Endpoint')
    return '\n'.join(lines)+'\n',addresses,mtu


OVPN_FLAGS={'client','nobind','persist-key','persist-tun','remote-cert-tls','verb','mute','auth-nocache','resolv-retry','connect-retry','connect-timeout','connect-retry-max','tls-client','tls-version-min','tls-version-max','cipher','data-ciphers','data-ciphers-fallback','auth','key-direction','tls-cipher','tls-ciphersuites','reneg-sec','ping','ping-restart','keepalive','explicit-exit-notify','tun-mtu','mssfix','sndbuf','rcvbuf','verify-x509-name','remote-random','float','auth-retry'}
INLINE={'ca','cert','key','tls-auth','tls-crypt','tls-crypt-v2','auth-user-pass'}


def openvpn_config(raw,endpoints):
    result=[];block=None;seen=set();remotes=[];transport=None
    for line in raw.decode().splitlines():
        stripped=line.strip()
        if block:
            result.append(line)
            if stripped==f'</{block}>':block=None
            continue
        if not stripped or stripped.startswith(('#',';')):continue
        if stripped.startswith('<'):
            name=stripped[1:-1]
            if name not in INLINE:raise ValueError('Недопустимый OpenVPN inline block')
            block=name;result.append(stripped);continue
        parts=shlex.split(stripped,comments=True)
        if not parts:continue
        k=parts[0];seen.add(k)
        if k=='dev':
            if parts!=['dev','tun0']:raise ValueError('OpenVPN dev должен быть tun0')
        elif k=='proto':
            if parts not in (['proto','udp'],['proto','udp4'],['proto','tcp-client'],['proto','tcp4-client']):raise ValueError('Недопустимый proto')
            transport='udp' if parts[1].startswith('udp') else 'tcp'
        elif k=='remote':
            if len(parts)!=3:raise ValueError('remote: literal IPv4 и порт')
            public4(parts[1]);integer(int(parts[2]),1,65535);remotes.append((parts[1],int(parts[2])))
        elif k not in OVPN_FLAGS:
            raise ValueError(f'OpenVPN directive запрещена: {k}; используйте inline credentials')
        if any('\x00' in x for x in parts):raise ValueError('NUL в конфигурации')
        result.append(stripped)
    if block or not {'client','dev','proto','remote','remote-cert-tls'}<=seen:raise ValueError('Неполный OpenVPN client config')
    for ip,port in remotes:endpoint_allowed(ip,port,transport,endpoints)
    # Ignore server-pushed routing and DNS; firewall remains authoritative.
    return '\n'.join(result)+'\nscript-security 0\nroute-nopull\npull-filter ignore "redirect-gateway"\npull-filter ignore "dhcp-option"\nauth-nocache\nverb 1\n'


def xray_config(raw,endpoints):
    data=json.loads(raw)
    keys(data,{'outbounds'},{'outbounds'})
    outs=data['outbounds']
    if not isinstance(outs,list) or not outs:raise ValueError('Нужен VLESS outbound')
    count=0
    for out in outs:
        keys(out,{'protocol','settings','streamSettings','tag'},{'protocol','settings'})
        if out['protocol']=='blackhole':continue
        if out['protocol']!='vless':raise ValueError('Разрешены только vless и blackhole')
        count+=1
        keys(out['settings'],{'vnext'},{'vnext'})
        nodes=out['settings']['vnext']
        if not isinstance(nodes,list) or len(nodes)!=1:raise ValueError('Ожидается один VLESS server')
        node=nodes[0];keys(node,{'address','port','users'},{'address','port','users'})
        endpoint_allowed(public4(node['address']),integer(node['port'],1,65535),'tcp',endpoints)
        if not isinstance(node['users'],list) or len(node['users'])!=1:raise ValueError('Ожидается один VLESS user')
        keys(node['users'][0],{'id','encryption','flow','level'},{'id'})
        stream=out.get('streamSettings',{})
        keys(stream,{'network','security','tlsSettings','realitySettings','grpcSettings','wsSettings','tcpSettings','xhttpSettings','httpupgradeSettings'})
        if stream.get('network','tcp') not in ('tcp','raw','grpc','ws','xhttp','httpupgrade'):raise ValueError('Transport не поддерживается')
        if stream.get('security','none') not in ('none','tls','reality'):raise ValueError('Security не поддерживается')
    if count!=1 or outs[0]['protocol']!='vless':raise ValueError('Первый и единственный VLESS — default outbound')
    return {'log':{'loglevel':'warning'},'inbounds':[{'tag':'transparent','port':12345,'protocol':'dokodemo-door','settings':{'network':'tcp,udp','followRedirect':True},'streamSettings':{'sockopt':{'tproxy':'tproxy'}}},{'tag':'health','listen':'127.0.0.1','port':1080,'protocol':'socks','settings':{'udp':True}}],'outbounds':outs}


def validate_vpn(kind,raw,endpoints):
    if not isinstance(raw,bytes) or len(raw)>1024*1024:raise ValueError('VPN config ограничен 1 MiB')
    {'wireguard':wireguard_config,'openvpn':openvpn_config,'xray':xray_config}[kind](raw,endpoints)


def save(path,data):
    p=validate(data);path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(p,f,indent=2);f.write('\n')


def load(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise ValueError('Профиль должен быть обычным файлом')
    if path.stat().st_mode & 0o077:raise ValueError('Профиль должен иметь права 0600')
    return validate(json.loads(path.read_text()))
