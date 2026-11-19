"""Nonprivileged PID 1 child; desktop stays available for CLI OAuth too."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from common import config

c=config();children=[];stopping=False

def stop(signum,frame):
    global stopping
    stopping=True
    for p in children:
        if p.poll() is None:p.terminate()

signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
# Disable desktop clipboard transfer in both directions.
children.append(subprocess.Popen(['Xtigervnc',':0','-geometry','1280x800','-depth','24','-rfbport','5900','-localhost','no','-SecurityTypes','VncAuth','-PasswordFile','/run/agent/vnc.passwd','-AcceptCutText=0','-SendCutText=0','-AlwaysShared']))
for _ in range(100):
    if Path('/tmp/.X11-unix/X0').exists():break
    if children[0].poll() is not None:sys.exit(1)
    time.sleep(.1)
else:sys.exit(1)
children.append(subprocess.Popen(['fluxbox']))
children.append(subprocess.Popen(['xterm','-title','AgentBox','-e','bash']))
if c['mode']=='gui':children.append(subprocess.Popen(c['gui']))
while not stopping and children[0].poll() is None:time.sleep(.25)
stop(None,None)
for p in children:
    try:p.wait(timeout=5)
    except subprocess.TimeoutExpired:p.kill()
