import unittest
from capture_uplink import summarize_capture


class CaptureEvidence(unittest.TestCase):
    allowed = {('203.0.113.10', 443, 'tcp')}

    def test_endpoint_packets_pass_and_blank_lines_are_ignored(self):
        report = summarize_capture(['1.0 IP 172.20.0.2.40000 > 203.0.113.10.443: tcp 0', ''], self.allowed, 5)
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['endpoint_transport_packets'], 1)

    def test_forwarded_agent_source_does_not_hide_direct_egress(self):
        report = summarize_capture([
            '1.0 IP 172.20.0.2.40000 > 203.0.113.10.443: tcp 0',
            '1.1 IP 172.21.0.3.50000 > 1.1.1.1.443: tcp 0',
        ], self.allowed, 5)
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['violating_packets'], 1)

    def test_ipv6_or_unknown_frames_fail_closed(self):
        for line in ['1.0 IP6 ::1.40000 > 2606:4700::1111.443: tcp 0', 'unrecognized frame']:
            with self.subTest(line=line):
                report = summarize_capture([line], self.allowed, 5)
                self.assertEqual(report['status'], 'FAIL')
                self.assertEqual(report['unparsed_lines'], 1)

    def test_empty_capture_is_not_evidence(self):
        self.assertEqual(summarize_capture([], self.allowed, 5)['status'], 'FAIL')
