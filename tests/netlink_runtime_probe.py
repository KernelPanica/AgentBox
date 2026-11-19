"""Narrow per-interface netlink forwarding; /proc/sys remains read-only.

Linux inet_set_link_af accepts IFLA_AF_SPEC/AF_INET/IFLA_INET_CONF.
Never enables forwarding on the external interface or in default/all.
"""
import os
import socket
import struct


def attribute(kind,payload):
    length=4+len(payload)
    return struct.pack('HH',length,kind)+payload+b'\0'*((-length)%4)


def forwarding_message(index,enabled,seq):
    config=attribute(1,struct.pack('I',int(enabled))) # IPV4_DEVCONF_FORWARDING
    af=attribute(0x8000|1,config) # IFLA_INET_CONF
    family=attribute(0x8000|socket.AF_INET,af)
    attrs=attribute(0x8000|26,family) # IFLA_AF_SPEC
    body=struct.pack('BBHiII',socket.AF_UNSPEC,0,0,index,0,0)+attrs
    return struct.pack('IHHII',16+len(body),16,5,seq,0)+body # RTM_NEWLINK REQUEST|ACK


def set_forwarding(interface,enabled=True):
    index=socket.if_nametoindex(interface);seq=os.getpid() & 0xffffffff
    with socket.socket(socket.AF_NETLINK,socket.SOCK_RAW,socket.NETLINK_ROUTE) as s:
        s.settimeout(3);s.bind((0,0));s.sendto(forwarding_message(index,enabled,seq),(0,0))
        while True:
            data=s.recv(8192);off=0
            while off+16<=len(data):
                size,kind,flags,number,pid=struct.unpack_from('IHHII',data,off)
                if size<16:raise RuntimeError('Malformed netlink reply')
                if number==seq and kind==2:
                    error=struct.unpack_from('i',data,off+16)[0]
                    if error:raise OSError(-error,os.strerror(-error))
                    return
                off+=(size+3)&~3

from pathlib import Path
import subprocess
before=Path('/proc/sys/net/ipv4/ip_forward').read_text()
subprocess.run(['ip','link','add','abprobe0','type','dummy'],check=True)
try:
    set_forwarding('abprobe0',True)
    assert Path('/proc/sys/net/ipv4/conf/abprobe0/forwarding').read_text().strip()=='1'
    set_forwarding('abprobe0',False)
    assert Path('/proc/sys/net/ipv4/conf/abprobe0/forwarding').read_text().strip()=='0'
    assert Path('/proc/sys/net/ipv4/ip_forward').read_text()==before
    print('PASS: per-interface forwarding on/off via netlink; global forwarding unchanged; proc/sys stays read-only')
finally:subprocess.run(['ip','link','delete','abprobe0'],check=True)
