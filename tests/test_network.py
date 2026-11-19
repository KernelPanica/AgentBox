import copy
import ipaddress
import tempfile
import unittest
from pathlib import Path
from test_config import profile
from agentboxlib.compose import render, network_plan
from runtime.policy import agent_rules, gateway_rules, relay_rules

class Network(unittest.TestCase):
    def setUp(self):
        self.p=profile(); self.net=network_plan('demo',[])
    def test_network_allocation_avoids_existing_subnets(self):
        n=network_plan('demo',[self.net['enclave_subnet'],self.net['uplink_subnet']])
        for key in ['enclave_subnet','uplink_subnet','ui_subnet']:
            for existing in self.net.values():
                if isinstance(existing,str) and '/' in existing:
                    self.assertFalse(ipaddress.ip_network(n[key]).overlaps(ipaddress.ip_network(existing)))
    def test_compose_has_no_host_mounts_or_agent_external_network(self):
        with tempfile.TemporaryDirectory() as d:
            c=render(self.p,Path(d),self.net)
        a=c['services']['agent']
        self.assertEqual(list(a['networks']),['enclave'])
        self.assertNotIn('ports',a)
        self.assertEqual(a['cap_drop'],['ALL'])
        self.assertNotIn('NET_RAW',a['cap_add'])
        self.assertTrue(c['networks']['enclave']['internal'])
        self.assertEqual(c['networks']['enclave']['driver_opts']['com.docker.network.bridge.gateway_mode_ipv4'],'isolated')
        self.assertEqual(c['services']['relay']['ports'],['127.0.0.1:6080:6080'])
        self.assertFalse(any('docker.sock' in str(v) for s in c['services'].values() for v in s.get('volumes',[])))
    def test_vpn_secret_only_in_gateway(self):
        with tempfile.TemporaryDirectory() as d:c=render(self.p,Path(d),self.net)
        self.assertTrue(any(v.get('target')=='/secrets/vpn.conf' for v in c['services']['gateway']['volumes'] if isinstance(v,dict)))
        for name in ['agent','relay']:
            self.assertFalse(any('vpn.conf' in str(v) for v in c['services'][name]['volumes']))
    def test_firewall_contract(self):
        cfg={**self.net,'kind':'wireguard','endpoints':self.p['vpn']['endpoints']}
        a=agent_rules(cfg)
        self.assertIn('ip daddr 127.0.0.11 drop',a)
        self.assertIn('policy drop',a)
        self.assertIn('meta nfproto ipv6 drop',a)
        g=gateway_rules(cfg,'eth1','10.99.1.1')
        self.assertIn('ip daddr 8.8.8.8 udp dport 51820',g)
        self.assertIn('type filter hook egress device "eth1"',g)
        self.assertIn('oifname "tun0"',g)
        r=relay_rules(cfg)
        self.assertIn('tcp dport 5900',r)
        self.assertIn('chain forward { type filter hook forward priority filter; policy drop;',r)
    def test_config_image_does_not_override_entrypoint(self):
        with tempfile.TemporaryDirectory() as d:c=render(self.p,Path(d),self.net)
        self.assertEqual(c['services']['agent']['entrypoint'],['python3','/opt/agentbox/agent.py'])
        self.assertEqual(c['services']['agent']['restart'],'no')
    def test_gateway_cannot_forward_during_bootstrap(self):
        with tempfile.TemporaryDirectory() as d:c=render(self.p,Path(d),self.net)
        self.assertEqual(c['services']['gateway']['sysctls']['net.ipv4.ip_forward'],'0')
    def test_agent_readiness_gates_relay(self):
        with tempfile.TemporaryDirectory() as d:c=render(self.p,Path(d),self.net)
        self.assertIn('healthcheck',c['services']['agent'])
        self.assertEqual(c['services']['relay']['depends_on']['agent']['condition'],'service_healthy')
    def test_equal_profile_names_in_distinct_directories_have_distinct_resources(self):
        with tempfile.TemporaryDirectory() as d:
            c1=render(self.p,Path(d)/'one',self.net)
            c2=render(self.p,Path(d)/'two',self.net)
            self.assertNotEqual(c1['name'],c2['name'])
    def test_relay_readiness_is_a_real_service_healthcheck(self):
        with tempfile.TemporaryDirectory() as d:c=render(self.p,Path(d),self.net)
        self.assertIn('healthcheck',c['services']['relay'])
