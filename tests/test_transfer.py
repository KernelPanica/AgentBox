import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from agentboxlib.transfer import pack, unpack

class Transfer(unittest.TestCase):
    def test_round_trip_without_host_path_names(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'source').mkdir();(root/'source/a.txt').write_text('ok')
            data=pack(root/'source');unpack(data,root/'result')
            self.assertEqual((root/'result/source/a.txt').read_text(),'ok')
    def test_symlink_source_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'link').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):pack(root/'link')
    def test_parent_symlink_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'real').mkdir();(root/'real/file').write_text('x');(root/'link').symlink_to(root/'real',target_is_directory=True)
            with self.assertRaises(ValueError):pack(root/'link/file')
    def test_tar_escape_link_and_devices_refused(self):
        for name,typ in [('../escape',tarfile.REGTYPE),('/etc/escape',tarfile.REGTYPE),('link',tarfile.SYMTYPE),('device',tarfile.CHRTYPE)]:
            with tempfile.TemporaryDirectory() as d:
                stream=io.BytesIO()
                with tarfile.open(fileobj=stream,mode='w') as t:
                    info=tarfile.TarInfo(name);info.type=typ;info.linkname='/etc';t.addfile(info)
                with self.subTest(name=name), self.assertRaises(ValueError):unpack(stream.getvalue(),Path(d)/'out')
                self.assertFalse((Path(d)/'escape').exists())
    def test_existing_destination_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'a').write_text('one');data=pack(root/'a');(root/'out').mkdir()
            with self.assertRaises(FileExistsError):unpack(data,root/'out')
    def test_root_and_home_parent_aliases_refused(self):
        from agentboxlib.transfer import safe_source
        for path in [Path('/tmp/..'),Path.home().parent/'alias'/ '..'/Path.home().name]:
            with self.subTest(path=path),self.assertRaises(ValueError):safe_source(path)
