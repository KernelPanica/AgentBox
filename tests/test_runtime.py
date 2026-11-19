import unittest
from agentboxlib.config import wireguard_config,openvpn_config
from runtime.health import parse_exit
from runtime.common import drop_command

class Runtime(unittest.TestCase):
    def test_wireguard_separates_addresses_from_setconf(self):
        raw=b'[Interface]\nPrivateKey = test\nAddress = 10.8.0.2/32\nMTU = 1380\n[Peer]\nPublicKey = test\nEndpoint = 8.8.8.8:443\nAllowedIPs = 0.0.0.0/0\n'
        text,addresses,mtu=wireguard_config(raw,[{'ip':'8.8.8.8','port':443,'protocol':'udp'}])
        self.assertNotIn('Address',text);self.assertNotIn('MTU',text)
        self.assertEqual(addresses,['10.8.0.2/32']);self.assertEqual(mtu,1380)
    def test_health_rejects_html_private_ip_and_unexpected_exit(self):
        for body in ['<html>fail</html>','10.0.0.1','::1','8.8.8.8\n1.1.1.1']:
            with self.subTest(body=body),self.assertRaises(ValueError):parse_exit(body,'')
        with self.assertRaises(ValueError):parse_exit('8.8.8.8','1.1.1.1')
        self.assertEqual(parse_exit('8.8.8.8\n','8.8.8.8'),'8.8.8.8')
    def test_application_drop_has_zero_bounding_caps_and_no_new_privileges(self):
        cmd=drop_command(['tini','--','bash'],1000)
        self.assertIn('--bounding-set=-all',cmd)
        self.assertIn('--no-new-privs',cmd)
        self.assertEqual(cmd[-3:],['tini','--','bash'])
    def test_transparent_proxy_accept_is_not_counted_as_remote_success(self):
        import socket
        import threading
        from runtime.probe import tls_exchange
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen()
        def accept_then_close():
            conn,_=listener.accept();conn.close();listener.close()
        t=threading.Thread(target=accept_then_close);t.start()
        self.assertFalse(tls_exchange('127.0.0.1',listener.getsockname()[1]));t.join()
