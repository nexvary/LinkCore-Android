import unittest

from direct_mttl_lab import BOOT_RE, normalize_mac, parse_getinfo


class DirectMttlLabParserTests(unittest.TestCase):
    def test_bootinfo(self):
        frame = "up:bootinfo:lgutap;A1B2C3D4E5F6;A1B2C3D4E5F6;1.0.66-0.1.54;connect"
        match = BOOT_RE.fullmatch(frame)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(2), match.group(3))

    def test_mac_normalization(self):
        self.assertEqual(normalize_mac("a1:b2:c3:d4:e5:f6"), "A1B2C3D4E5F6")

    def test_getinfo_requires_four_channels(self):
        self.assertIsNone(parse_getinfo("up:getinfo:1:x"))


if __name__ == "__main__":
    unittest.main()
