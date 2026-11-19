from common import config,firewall,drop_exec
from policy import relay_rules
c=config();firewall(relay_rules(c))
drop_exec(['tini','--','websockify','--web=/usr/share/novnc','6080',c['agent_ip']+':5900'],900)
