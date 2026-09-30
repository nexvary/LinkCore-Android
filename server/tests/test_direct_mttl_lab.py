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

    def test_getinfo_partial_live_frame(self):
        frame = (
            "up:getinfo:"
            "1:0;on;3;on;on;0;00000000;00000000;00000000;off;00;25:"
            "3:0;on;3;on;on;0;00000000;00000000;00000000;off;00;24:"
            "4:0;on;3;on;on;0;00000000;00000000;00000000;off;00;26"
        )
        parsed = parse_getinfo(frame)
        self.assertIsNotNone(parsed)
        self.assertEqual([item["channel"] for item in parsed], [1, 3, 4])
        self.assertEqual(parsed[0]["temperature_c"], 25)

    def test_getinfo_field_capture_from_mttl_w01(self):
        block = "0;on;3;on;on;0;00000000;00000000;00000000;off;00;25"
        frame = "up:getinfo:" + ":".join(
            [f"{channel}:{block}" for channel in range(1, 5)]
        )
        parsed = parse_getinfo(frame)
        self.assertIsNotNone(parsed)
        self.assertEqual([item["channel"] for item in parsed], [1, 2, 3, 4])
        self.assertEqual(parsed[0]["relay"], "on")
        self.assertEqual(parsed[0]["temperature_c"], 25)

    def test_getinfo_tolerates_trailing_firmware_field(self):
        block = "0;off;3;on;on;0;00000000;00000000;00000000;off;00;26;extra"
        frame = "up:getinfo:" + ":".join(
            [f"{channel}:{block}" for channel in range(1, 5)]
        )
        parsed = parse_getinfo(frame)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed[3]["temperature_c"], 26)


if __name__ == "__main__":
    unittest.main()
