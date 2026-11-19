import sys
from pathlib import Path
from agentboxlib.transfer import pack,unpack,LIMIT
try:
    action,path=sys.argv[1:]
    if action=='import':unpack(sys.stdin.buffer.read(LIMIT+1),Path(path))
    elif action=='export':sys.stdout.buffer.write(pack(Path(path)))
    else:raise ValueError('Unknown operation')
except Exception:
    print('Обмен файлами отклонён',file=sys.stderr);sys.exit(1)
