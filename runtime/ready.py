import socket
import sys
from pathlib import Path
try:
    status=dict(line.split(':',1) for line in Path('/proc/1/status').read_text().splitlines() if ':' in line)
    assert status['Uid'].split()[0]=='1000' and int(status['CapBnd'].strip(),16)==0
    with socket.create_connection(('127.0.0.1',5900),timeout=1) as s:
        assert s.recv(12).startswith(b'RFB ')
except Exception:sys.exit(1)
