import struct
import unittest
from runtime.forwarding import forwarding_message

class Forwarding(unittest.TestCase):
    def test_kernel_message_sets_only_requested_interface_forwarding(self):
        data=forwarding_message(7,True,42)
        size,kind,flags,seq,pid=struct.unpack_from('IHHII',data)
        self.assertEqual((size,kind,flags,seq),(len(data),16,5,42))
        family,pad,typ,index,linkflags,change=struct.unpack_from('BBHiII',data,16)
        self.assertEqual((family,index,linkflags,change),(0,7,0,0))
        # Four nested nlattrs: AF_SPEC(26), AF_INET(2), INET_CONF(1), FORWARDING(1).
        off=32
        for expected in [26|0x8000,2|0x8000,1|0x8000,1]:
            length,typ=struct.unpack_from('HH',data,off);self.assertEqual(typ,expected);off+=4
        self.assertEqual(struct.unpack_from('I',data,off)[0],1)
        self.assertEqual(struct.unpack_from('I',forwarding_message(7,False,43),off)[0],0)
