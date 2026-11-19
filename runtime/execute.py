"""Docker-admin-only launcher; commands get the same zero-capability identity as PID 1."""
import os
import sys
from common import drop_exec
os.chdir('/workspace')
os.environ.update(HOME='/home/agent',DISPLAY=':0',XDG_RUNTIME_DIR='/run/user/1000',BROWSER='/usr/local/bin/agentbox-browser',TZ='UTC',LANG='en_US.UTF-8',LC_ALL='en_US.UTF-8')
drop_exec(sys.argv[1:])
