import unittest
from unittest.mock import patch

import config
from action import Action, KeyComboListener, PRIORITY_HEAL, PRIORITY_LOOT
from pynput.keyboard import Key, KeyCode
from state import SharedState


class DispatcherCooldownTests(unittest.TestCase):
    def test_dispatch_skips_when_global_cooldown_active(self) -> None:
        action = Action()
        action._queue = [(PRIORITY_HEAL, "h", "health")]
        action._last_automated_input = 100.0
        action.press_async = lambda *args, **kwargs: None

        with patch.object(config, "GLOBAL_ACTION_COOLDOWN", 0.15):
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

    def test_listener_tracks_non_bot_physical_keys(self) -> None:
        original = {
            "HEALTH": config.HEALTH.keybind,
            "MANA": config.MANA.keybind,
            "LOOTING_KEYBIND": config.LOOTING_KEYBIND,
            "LOOTING_TOGGLE_1": config.LOOTING_TOGGLE_1,
            "LOOTING_TOGGLE_2": config.LOOTING_TOGGLE_2,
            "REPOT_TOGGLE_1": config.REPOT_TOGGLE_1,
            "REPOT_TOGGLE_2": config.REPOT_TOGGLE_2,
            "REBFF_TOGGLE_1": config.REBUFF_TOGGLE_1,
            "REBFF_TOGGLE_2": config.REBUFF_TOGGLE_2,
        }
        try:
            config.HEALTH.keybind = "h"
            config.MANA.keybind = "m"
            config.LOOTING_KEYBIND = "x"
            config.LOOTING_TOGGLE_1 = "j"
            config.LOOTING_TOGGLE_2 = "k"
            config.REPOT_TOGGLE_1 = "u"
            config.REPOT_TOGGLE_2 = "i"
            config.REBUFF_TOGGLE_1 = "o"
            config.REBUFF_TOGGLE_2 = "p"

            state = SharedState()
            listener = KeyComboListener(state)

            with patch.object(config, "load_schedules", return_value=[]):
                listener.on_press(KeyCode.from_char("a"))
                listener.on_press(KeyCode.from_char("x"))
                self.assertEqual(state.get("physical_keys_held"), 1)
                self.assertEqual(listener._physical, {"a", "x"})

                listener.on_release(KeyCode.from_char("a"))
                self.assertEqual(state.get("physical_keys_held"), 0)
        finally:
            config.HEALTH.keybind = original["HEALTH"]
            config.MANA.keybind = original["MANA"]
            config.LOOTING_KEYBIND = original["LOOTING_KEYBIND"]
            config.LOOTING_TOGGLE_1 = original["LOOTING_TOGGLE_1"]
            config.LOOTING_TOGGLE_2 = original["LOOTING_TOGGLE_2"]
            config.REPOT_TOGGLE_1 = original["REPOT_TOGGLE_1"]
            config.REPOT_TOGGLE_2 = original["REPOT_TOGGLE_2"]
            config.REBUFF_TOGGLE_1 = original["REBFF_TOGGLE_1"]
            config.REBUFF_TOGGLE_2 = original["REBFF_TOGGLE_2"]

    def test_listener_clears_physical_count_on_stop(self) -> None:
        state = SharedState()
        listener = KeyComboListener(state)

        listener.on_press(KeyCode.from_char("a"))
        listener.stop()

        self.assertEqual(listener._physical, set())
        self.assertEqual(state.get("physical_keys_held"), 0)

    def test_trigger_defers_when_resolution_limit_active(self) -> None:
        state = SharedState()
        action = Action(state)
        action.press_async = lambda *args, **kwargs: None
        state.set("last_input_timestamp", 100.0)

        with patch.object(config, "GLOBAL_RESOLUTION_LIMIT", 0.1):
            with patch("action.time.perf_counter", side_effect=[100.05, 100.05]):
                self.assertFalse(action.trigger("h", 0.0, "health"))

    def test_listener_ignores_movement_and_bot_keys(self) -> None:
        original = {
            "HEALTH": config.HEALTH.keybind,
            "MANA": config.MANA.keybind,
            "LOOTING_KEYBIND": config.LOOTING_KEYBIND,
            "LOOTING_TOGGLE_1": config.LOOTING_TOGGLE_1,
            "LOOTING_TOGGLE_2": config.LOOTING_TOGGLE_2,
            "REPOT_TOGGLE_1": config.REPOT_TOGGLE_1,
            "REPOT_TOGGLE_2": config.REPOT_TOGGLE_2,
            "REBFF_TOGGLE_1": config.REBUFF_TOGGLE_1,
            "REBFF_TOGGLE_2": config.REBUFF_TOGGLE_2,
        }
        try:
            config.HEALTH.keybind = "h"
            config.MANA.keybind = "m"
            config.LOOTING_KEYBIND = "x"
            config.LOOTING_TOGGLE_1 = "j"
            config.LOOTING_TOGGLE_2 = "k"
            config.REPOT_TOGGLE_1 = "u"
            config.REPOT_TOGGLE_2 = "i"
            config.REBUFF_TOGGLE_1 = "o"
            config.REBUFF_TOGGLE_2 = "p"

            state = SharedState()
            listener = KeyComboListener(state)

            with patch.object(config, "load_schedules", return_value=[]):
                listener.on_press(KeyCode.from_char("a"))
                listener.on_press(KeyCode.from_char("b"))
                listener.on_press(Key.left)
                listener.on_press(Key.space)

            self.assertEqual(state.get("physical_keys_held"), 2)
        finally:
            config.HEALTH.keybind = original["HEALTH"]
            config.MANA.keybind = original["MANA"]
            config.LOOTING_KEYBIND = original["LOOTING_KEYBIND"]
            config.LOOTING_TOGGLE_1 = original["LOOTING_TOGGLE_1"]
            config.LOOTING_TOGGLE_2 = original["LOOTING_TOGGLE_2"]
            config.REPOT_TOGGLE_1 = original["REPOT_TOGGLE_1"]
            config.REPOT_TOGGLE_2 = original["REPOT_TOGGLE_2"]
            config.REBUFF_TOGGLE_1 = original["REBFF_TOGGLE_1"]
            config.REBUFF_TOGGLE_2 = original["REBFF_TOGGLE_2"]


if __name__ == "__main__":
    unittest.main()
