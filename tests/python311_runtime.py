#!/usr/bin/env python3
"""Compile actual source using the Debian 12 relay's real Python 3.11 parser."""
import subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
code="from pathlib import Path;import sys;files=list(Path('/src/runtime').glob('*.py'))+list(Path('/src/lib').glob('*.py'));[compile(p.read_text(),str(p),'exec') for p in files];print('PASS:',len(files),'production modules compiled with Python',sys.version.split()[0])"
subprocess.run(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','-v',str(root/'runtime')+':/src/runtime:ro','-v',str(root/'agentboxlib')+':/src/lib:ro','--entrypoint','python3','agentbox-relay:local','-c',code],check=True)
