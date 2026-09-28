"""Exact vendor-frame contract for Ambience schedule writes."""

import importlib.util
from pathlib import Path
import sys
import unittest


SOURCE = Path(__file__).parents[1] / "custom_components/ambience/protocol.py"
SPEC = importlib.util.spec_from_file_location("ambience_protocol_under_test", SOURCE)
protocol = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = protocol
SPEC.loader.exec_module(protocol)


class ScheduleWriteTest(unittest.TestCase):
    def test_intensity_two_completes_second_fragment(self):
        reported = bytes.fromhex("01 01 00 01 01 ff 08 00 12 00 01 00 00 00 00")

        frames = protocol.schedule_from_raw(reported, intensity=2)

        self.assertEqual(frames, [
            bytes.fromhex("25 01 ff 01 03 e9 af 00 0f 01 01 01 01 01 ff 08 00 12 00 02"),
            bytes.fromhex("25 02 00 00 00 00"),
        ])
        self.assertEqual(reported[5:11], bytes.fromhex("ff 08 00 12 00 01"))

    def test_edit_preserves_other_schedule_fields(self):
        reported = bytes.fromhex("01 00 03 01 01 82 06 00 14 00 01 00 00 00 00")

        frames = protocol.schedule_from_raw(reported, intensity=4)

        self.assertEqual(frames[0][9:19], bytes.fromhex("01 01 01 01 01 82 06 00 14 00"))
        self.assertEqual(frames[0][19], 4)
        self.assertEqual(frames[1], bytes.fromhex("25 02 00 00 00 00"))


if __name__ == "__main__":
    unittest.main()
