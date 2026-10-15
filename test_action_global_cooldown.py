import unittest
from unittest.mock import patch

import config
from action import Action


class GlobalCooldownTests(unittest.TestCase):
    def test_trigger_respects_global_cooldown(self) -> None:
        action = Action()
        action._last_automated_input = 100.0
        action.press_async = lambda *args, **kwargs: None

        with patch("action.time.perf_counter", return_value=100.05):
            self.assertFalse(action.trigger("a", cooldown=0.0))

    def test_manage_looting_respects_global_cooldown(self) -> None:
        action = Action()
        action._last_automated_input = 100.0
        action.press_async = lambda *args, **kwargs: None
        config.LOOTING_KEYBIND = "x"

        with patch("action.time.perf_counter", return_value=100.05):
            action.manage_looting(True)
            self.assertIsNone(action._loot_last_hold)


if __name__ == "__main__":
    unittest.main()
