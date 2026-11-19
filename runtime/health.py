import ipaddress
import json
import subprocess
import sys
from pathlib import Path


def parse_exit(body,expected):
    value=body.strip();ip=ipaddress.IPv4Address(value)
    if not ip.is_global or ip.is_multicast:raise ValueError('Nonpublic exit')
    if expected and value!=expected:raise ValueError('Unexpected exit')
    return value


def check(c):
    results=[]
    for url in ['https://api.ipify.org','https://ipv4.icanhazip.com']:
        args=['curl','--fail','--silent','--show-error','--max-time','9','--connect-timeout','5','--max-filesize','128','--ipv4','--noproxy','*']
        if c['kind']=='xray':args+=['--proxy','socks5h://127.0.0.1:1080','--noproxy','']
        r=subprocess.run([*args,url],capture_output=True,text=True)
        if r.returncode:raise ValueError('Tunnel HTTPS health failed')
        results.append(parse_exit(r.stdout,c.get('expected_exit_ip','')))
    if results[0]!=results[1]:raise ValueError('Exit services disagree')
    return results[0]


if __name__=='__main__':
    try:
        c=json.loads(Path('/etc/agentbox.json').read_text())
        print(check(c))
    except Exception:
        print('VPN health unavailable',file=sys.stderr);sys.exit(1)
