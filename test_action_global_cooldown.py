import unittest
from unittest.mock import patch

import config
from action import Action, PRIORITY_HEAL, PRIORITY_LOOT
from state import SharedState


class DispatcherCooldownTests(unittest.TestCase):
    def test_dispatch_skips_when_global_cooldown_active(self) -> None:
        action = Action()
        action._queue = [(PRIORITY_HEAL, "h", "health")]
        action._last_automated_input = 100.0
        action.press_async = lambda *args, **kwargs: None

        with patch("action.time.perf_counter", return_value=100.05):
            action._dispatch({})

        self.assertEqual(action._queue, [(PRIORITY_HEAL, "h", "health")])

    def test_collect_enqueues_loot_and_dispatches_once(self) -> None:
        config.LOOTING_KEYBIND = "x"
        state = SharedState({"looting_active": True})
        action = Action(state)
        action.press_async = lambda *args, **kwargs: None
        action._last_loot_tap = 0.0

        with patch("action.time.perf_counter", return_value=1.0):
            action._collect(
                state,
                {"looting_active": True, "repot_active": False, "rebuff_active": False},
            )
            self.assertIn((PRIORITY_LOOT, "x", "loot"), action._queue)
            action._dispatch({"looting_active": True, "repot_active": False, "rebuff_active": False})

        self.assertEqual(action._queue, [])


if __name__ == "__main__":
    unittest.main()
