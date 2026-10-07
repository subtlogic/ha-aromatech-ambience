"""Schedule saves require device readback, with one bounded retry."""

import asyncio
from collections import deque
from datetime import datetime
import importlib.util
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).parents[1] / "custom_components/aromatech_ambience"


def module(name, **attrs):
    result = types.ModuleType(name)
    result.__dict__.update(attrs)
    sys.modules[name] = result
    return result


module("bleak", BleakClient=type("BleakClient", (), {}))
module("bleak_retry_connector", establish_connection=None)
module("homeassistant")
module("homeassistant.components", bluetooth=None)
module("homeassistant.core", HomeAssistant=object, callback=lambda fn: fn)
module("homeassistant.exceptions", HomeAssistantError=type("HomeAssistantError", (Exception,), {}))
module("homeassistant.helpers")


class DataUpdateCoordinator:
    @classmethod
    def __class_getitem__(cls, _item):
        return cls


module("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=DataUpdateCoordinator,
       UpdateFailed=type("UpdateFailed", (Exception,), {}))
module("homeassistant.util", dt=types.SimpleNamespace(now=datetime.now, utcnow=datetime.utcnow))
module("aromatech_ambience", __path__=[str(ROOT)])
module("aromatech_ambience.const", DISCONNECT_DELAY=20, REPLY_TIMEOUT=5,
       SCAN_INTERVAL_SECONDS=300)

spec = importlib.util.spec_from_file_location("aromatech_ambience.protocol", ROOT / "protocol.py")
protocol = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = protocol
spec.loader.exec_module(protocol)
spec = importlib.util.spec_from_file_location("aromatech_ambience.coordinator", ROOT / "coordinator.py")
coordinator_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = coordinator_module
spec.loader.exec_module(coordinator_module)
coordinator_module.RETRY_BACKOFF = 0


def fake_coordinator(outcomes):
    coordinator = coordinator_module.AmbienceCoordinator.__new__(coordinator_module.AmbienceCoordinator)
    coordinator.data = protocol.State(intensity=2, days_mask=0xff, start_hour=8, end_hour=18,
                                      raw={protocol.CMD_POWER: bytes.fromhex("01 01 00 01 01 ff 08 00 12 00 02 00 00 00 00")})
    coordinator.commands = []
    replies = iter(outcomes)

    async def command(*, build):
        coordinator.commands.append(build(coordinator.data))
        if next(replies):
            coordinator.data.intensity = 3

    async def refresh():
        return None

    coordinator._command = command
    coordinator.async_request_refresh = refresh
    return coordinator


class ScheduleReadbackTest(unittest.TestCase):
    def test_light_off_reply_updates_mode_before_bare_on(self):
        coordinator = coordinator_module.AmbienceCoordinator.__new__(coordinator_module.AmbienceCoordinator)
        coordinator.data = protocol.State(light_mode=4, rgb=(255, 137, 14), brightness=30)

        async def exchange(_frames, *, build=None):
            return protocol.State(light_mode=0, rgb=(255, 137, 14), brightness=30)

        async def unexpected_refresh():
            self.fail("a state-carrying light reply should update immediately")

        coordinator._exchange = exchange
        coordinator.async_request_refresh = unexpected_refresh
        coordinator.async_set_updated_data = lambda value: setattr(coordinator, "data", value)

        asyncio.run(coordinator._command([b"light off"]))

        self.assertEqual(coordinator.data.light_mode, 0)

    def test_retries_ignored_write_then_confirms_value(self):
        coordinator = fake_coordinator([False, True])

        asyncio.run(coordinator.async_set_schedule(intensity=3))

        self.assertEqual(coordinator.data.intensity, 3)
        self.assertEqual(len(coordinator.commands), 2)
        self.assertEqual(coordinator.commands[0][1], bytes.fromhex("25 02 00 00 00 00"))

    def test_third_attempt_can_confirm_value(self):
        coordinator = fake_coordinator([False, False, True])

        asyncio.run(coordinator.async_set_schedule(intensity=3))

        self.assertEqual(coordinator.data.intensity, 3)
        self.assertEqual(len(coordinator.commands), 3)

    def test_raises_when_all_device_reports_keep_old_value(self):
        coordinator = fake_coordinator([False, False, False])

        with self.assertRaisesRegex(Exception, "did not retain schedule change"):
            asyncio.run(coordinator.async_set_schedule(intensity=3))

        self.assertEqual(coordinator.data.intensity, 2)
        self.assertEqual(len(coordinator.commands), 3)


if __name__ == "__main__":
    unittest.main()
