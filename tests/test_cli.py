import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_config import profile
from agentboxlib.engine import prepare, lock

ROOT=Path(__file__).resolve().parents[1]

class Lifecycle(unittest.TestCase):
    def test_prepare_creates_private_runtime_and_split_configs(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);vpn=root/'vpn.conf'
            vpn.write_text('[Interface]\nPrivateKey = test\nAddress = 10.8.0.2/32\n[Peer]\nPublicKey = test\nAllowedIPs = 0.0.0.0/0\nEndpoint = 8.8.8.8:51820\n');vpn.chmod(0o600)
            p=profile();p['vpn']['config']=str(vpn)
            state=prepare(p,root/'runtime',[])
            self.assertEqual((state/'vpn.conf').stat().st_mode & 0o777,0o600)
            a=json.loads((state/'agent.json').read_text())
            self.assertNotIn('endpoints',a);self.assertNotIn('vpn',a)
            self.assertNotIn('PrivateKey',(state/'compose.json').read_text())
            self.assertEqual(len((state/'vnc.password').read_text().strip()),8)
    def test_lock_rejects_second_owner(self):
        with tempfile.TemporaryDirectory() as d:
            with lock(Path(d)/'lock'):
                with self.assertRaises(ValueError):
                    with lock(Path(d)/'lock'):pass
    def test_cli_help_and_render_without_daemon(self):
        r=subprocess.run([str(ROOT/'agentbox'),'--help'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0);self.assertIn('configure',r.stdout)
        r=subprocess.run([str(ROOT/'agentbox'),'start','--profile','/nonexistent'],capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0)
        self.assertNotIn('Traceback',r.stderr)
    def test_prepare_rejects_world_readable_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);vpn=root/'vpn.conf';vpn.write_text('bad');vpn.chmod(0o644)
            p=profile();p['vpn']['config']=str(vpn)
            with self.assertRaises(ValueError):prepare(p,root/'runtime',[])

class HealthGate(unittest.TestCase):
    def test_unhealthy_gateway_refuses_application_execution(self):
        from unittest.mock import patch
        from agentboxlib.engine import require_healthy
        def daemon(args,**kwargs):
            if args[:3]==['inspect','--format','{{.State.Health.Status}}']:
                return subprocess.CompletedProcess(args,0,'unhealthy\n','')
            raise AssertionError(args)
        with tempfile.TemporaryDirectory() as d:
            state=Path(d);(state/'compose.json').write_text('{"name":"agentbox-test"}')
            with patch('agentboxlib.engine.compose',return_value=subprocess.CompletedProcess([],0,'gatewayid\n','')),patch('agentboxlib.engine.docker',side_effect=daemon):
                with self.assertRaises(ValueError):require_healthy(state)
    def test_runtime_bind_metadata_does_not_expose_home_path(self):
        from agentboxlib import engine
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);vpn=root/'vpn.conf'
            vpn.write_text('[Interface]\nPrivateKey = test\nAddress = 10.8.0.2/32\n[Peer]\nPublicKey = test\nAllowedIPs = 0.0.0.0/0\nEndpoint = 8.8.8.8:51820\n');vpn.chmod(0o600)
            p=profile();p['vpn']['config']=str(vpn)
            state=engine.prepare(p,root/'runtime',[])
            compose=json.loads((state/'compose.json').read_text())
            for service in compose['services'].values():
                for mount in service['volumes']:
                    if isinstance(mount,dict):self.assertTrue(mount['source'].startswith('/tmp/agentbox-runtime-'))
            engine.cleanup_mounts(state)
    def test_remote_docker_host_is_rejected_before_any_docker_action(self):
        from unittest.mock import patch
        from agentboxlib.engine import require_engine
        with patch.dict('os.environ',{'DOCKER_HOST':'tcp://remote.example:2375','DOCKER_CONTEXT':''}),patch('agentboxlib.engine.docker',side_effect=AssertionError('remote must not be contacted')):
            with self.assertRaises(ValueError):require_engine()
