"""nft rules for each trust boundary; installed atomically before child processes."""
PRIVATE='0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.0.0.0/24, 192.0.2.0/24, 192.168.0.0/16, 198.18.0.0/15, 198.51.100.0/24, 203.0.113.0/24, 224.0.0.0/4, 240.0.0.0/4'


def agent_rules(c):
    return f'''table inet agentbox {{
 set private4 {{ type ipv4_addr; flags interval; elements = {{ {PRIVATE} }} }}
 chain input {{ type filter hook input priority filter; policy drop;
   meta nfproto ipv6 drop
   iifname "lo" accept
   ct state established,related accept
   ip saddr {c['relay_ip']} tcp dport 5900 accept
 }}
 chain forward {{ type filter hook forward priority filter; policy drop; }}
 chain output {{ type filter hook output priority -150; policy drop;
   meta nfproto ipv6 drop
   ip daddr 127.0.0.11 drop
   oifname "lo" ip daddr 127.0.0.1 accept
   ip daddr {c['relay_ip']} tcp sport 5900 ct state established accept
   ip daddr @private4 drop
   meta l4proto {{ tcp, udp }} accept
 }}
}}'''


def gateway_rules(c,iface,gateway):
    # Values are generated from validated addresses; iface verified in bootstrap.
    endpoint='\n'.join(f"ip daddr {e['ip']} {e['protocol']} dport {e['port']} accept" for e in c['endpoints'])
    wire='\n'.join(f"ether type ip ip saddr {c['uplink_ip']} ip daddr {e['ip']} ip protocol {e['protocol']} {e['protocol']} dport {e['port']} accept" for e in c['endpoints'])
    isx=c['kind']=='xray'
    tproxy=f'''chain prerouting {{ type filter hook prerouting priority mangle; policy accept;
       ip saddr {c['agent_ip']} ip daddr @private4 drop
       ip saddr {c['agent_ip']} meta l4proto {{ tcp, udp }} tproxy ip to :12345 meta mark set 1 accept
    }}''' if isx else ''
    forward='' if isx else f'''ip saddr {c['agent_ip']} ip daddr @private4 drop
       iifname != "tun0" oifname "tun0" ip saddr {c['agent_ip']} meta l4proto {{ tcp, udp }} accept
       iifname "tun0" ip daddr {c['agent_ip']} ct state established,related accept'''
    return f'''table netdev agentbox_wire {{
 chain uplink {{ type filter hook egress device "{iface}" priority 0; policy drop;
   ether type arp arp saddr ip {c['uplink_ip']} arp daddr ip {gateway} arp operation {{ request, reply }} accept
   {wire}
   counter drop
 }}
}}
table inet agentbox {{
 set private4 {{ type ipv4_addr; flags interval; elements = {{ {PRIVATE} }} }}
 {tproxy}
 chain input {{ type filter hook input priority filter; policy drop;
   meta nfproto ipv6 drop
   iifname "lo" ip daddr 127.0.0.1 accept
   ct state established,related accept
   {'ip saddr '+c['agent_ip']+' meta mark 1 meta l4proto { tcp, udp } accept' if isx else ''}
 }}
 chain forward {{ type filter hook forward priority filter; policy drop;
   meta nfproto ipv6 drop
   {forward}
 }}
 chain output {{ type filter hook output priority -150; policy drop;
   meta nfproto ipv6 drop
   ip daddr 127.0.0.11 drop
   oifname "lo" ip daddr 127.0.0.1 accept
   {'ip daddr '+c['agent_ip']+' meta l4proto { tcp, udp } accept' if isx else ''}
   {endpoint}
   ip daddr @private4 drop
   {'' if isx else 'oifname "tun0" meta l4proto { tcp, udp } accept'}
 }}
}}
{'' if isx else 'table ip agentbox_nat {\n chain postrouting {\n type nat hook postrouting priority srcnat; policy accept;\n oifname "tun0" masquerade\n }\n}\n'}'''


def relay_rules(c):
    return f'''table inet agentbox {{
 chain input {{ type filter hook input priority filter; policy drop;
   meta nfproto ipv6 drop
   ct state established,related accept
   tcp dport 6080 accept
 }}
 chain forward {{ type filter hook forward priority filter; policy drop; }}
 chain output {{ type filter hook output priority -150; policy drop;
   meta nfproto ipv6 drop
   ip daddr 127.0.0.11 drop
   ct state established,related accept
   ip daddr {c['agent_ip']} tcp dport 5900 accept
 }}
}}'''
