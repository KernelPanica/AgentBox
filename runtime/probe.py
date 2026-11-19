"""Agent-side, nonprivileged runtime checks. JSON output contains no credentials."""
import ipaddress
import json
import os
import socket
import ssl
import struct
import subprocess
import sys
from pathlib import Path


def tcp(ip,port):
    try:
        with socket.create_connection((ip,port),timeout=2):return True
    except OSError:return False


def tls_exchange(ip,port):
    try:
        context=ssl.create_default_context()
        with socket.create_connection((ip,port),timeout=2) as raw:
            with context.wrap_socket(raw,server_hostname='cloudflare-dns.com') as secure:
                secure.sendall(b'GET /cdn-cgi/trace HTTP/1.1\r\nHost: cloudflare-dns.com\r\nConnection: close\r\n\r\n')
                return secure.recv(512).startswith(b'HTTP/1.1 200')
    except (OSError,ssl.SSLError):return False


def dns_exchange(tcp_mode=False):
    ident=os.urandom(2)
    request=ident+b'\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'+b'\x07example\x03com\x00\x00\x01\x00\x01'
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM if tcp_mode else socket.SOCK_DGRAM) as s:
            s.settimeout(2);s.connect(('1.1.1.1',53))
            if tcp_mode:
                s.sendall(struct.pack('!H',len(request))+request)
                size=s.recv(2)
                if len(size)!=2:return False
                response=s.recv(struct.unpack('!H',size)[0])
            else:s.send(request);response=s.recv(4096)
            return len(response)>=12 and response[:2]==ident and bool(response[2]&128) and response[3]&15==0
    except OSError:return False


def probe(blocked=False):
    results={}
    status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    pid1=dict(line.split(':',1) for line in Path('/proc/1/status').read_text().splitlines() if ':' in line)
    results['uid_1000']=os.getuid()==1000
    results['caps_zero']=all(int(status[k].strip(),16)==0 for k in ['CapEff','CapPrm','CapBnd','CapAmb'])
    results['pid1_unprivileged']=pid1['Uid'].split()[0]=='1000' and int(pid1['CapBnd'].strip(),16)==0
    results['no_new_privs']=status['NoNewPrivs'].strip()=='1'
    results['host_sockets_absent']=not any(Path(x).exists() for x in ['/var/run/docker.sock','/run/dbus/system_bus_socket','/tmp/.X11-unix/X1','/run/host','/host'])
    results['docker_dns_blocked']=not tcp('127.0.0.11',53)
    results['lan_blocked']=all(not tcp(ip,port) for ip,port in [('169.254.169.254',80),('192.168.1.1',80),('172.17.0.1',80)])
    try:
        s=socket.socket(socket.AF_INET6,socket.SOCK_STREAM);s.settimeout(1)
        try:s.connect(('2606:4700:4700::1111',443));v6=True
        except OSError:v6=False
        finally:s.close()
    except OSError:v6=False
    results['ipv6_blocked']=not v6
    try: dns=subprocess.run(['getent','ahostsv4','example.com'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=12).returncode==0
    except subprocess.TimeoutExpired: dns=False
    r=subprocess.run(['curl','-4','--noproxy','*','--fail','--silent','--max-time','8','https://api.ipify.org'],capture_output=True,text=True)
    literal=tls_exchange('1.1.1.1',443)
    udp_dns=dns_exchange(False);tcp_dns=dns_exchange(True)
    if blocked:
        results.update(dns_blocked=not dns,udp_dns_blocked=not udp_dns,tcp_dns_blocked=not tcp_dns,https_blocked=r.returncode!=0,literal_tcp_blocked=not literal)
    else:
        results.update(dns_through_vpn=dns,udp_dns_through_vpn=udp_dns,tcp_dns_through_vpn=tcp_dns,https_through_vpn=r.returncode==0,literal_tcp_through_vpn=literal)
    return results


if __name__=='__main__':
    try:
        r=probe('--blocked' in sys.argv);print(json.dumps(r));sys.exit(0 if all(r.values()) else 1)
    except Exception:
        print(json.dumps({'probe_execution':False}));sys.exit(1)
