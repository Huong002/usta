import contextlib
import asyncio
import os
import sys
import threading
import unittest
from unittest import mock

from usta.core.shortcut import GlobalHotkey, keyboard


class PlatformHotkeyTests(unittest.TestCase):
    def test_wayland_hotkey_uses_portal_backend(self):
        backend = mock.Mock()
        with (
            mock.patch("usta.core.shortcut.sys.platform", "linux"),
            mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland"}),
            mock.patch(
                "usta.core.shortcut._load_wayland_hotkey", return_value=mock.Mock(return_value=backend)
            ) as load_portal,
        ):
            hotkey = GlobalHotkey("<shift>+<alt>+t", lambda: None)
            self.assertTrue(hotkey.start())
            portal_type = load_portal.return_value
            portal_type.assert_called_once_with("<shift>+<alt>+t", hotkey.callback)
            backend.start.assert_called_once()
            hotkey.stop()
            backend.stop.assert_called_once()

    def test_portal_trigger_uses_xdg_shortcut_syntax(self):
        from usta.core.platform.linux.global_shortcuts import to_portal_trigger

        self.assertEqual(to_portal_trigger("<shift>+<alt>+t"), "SHIFT+ALT+t")
        self.assertEqual(to_portal_trigger("<ctrl>+<alt>+f9"), "CTRL+ALT+F9")

    def test_wayland_bind_shortcuts_request_marshals_struct_as_list(self):
        from dbus_next import Variant
        from dbus_next.message import Message
        from usta.core.platform.linux.global_shortcuts import WaylandGlobalHotkey

        async def scenario():
            hotkey = WaylandGlobalHotkey("<alt>+c", lambda: None)
            hotkey._bus = mock.Mock()
            hotkey._bus.connect = mock.AsyncMock(return_value=hotkey._bus)
            hotkey._stopping = asyncio.Event()
            hotkey._stopping.set()
            hotkey._register_app_id = mock.AsyncMock()
            hotkey._add_match = mock.AsyncMock()
            hotkey._portal_request = mock.AsyncMock(
                side_effect=[
                    {"session_handle": Variant("o", "/portal/session/usta")},
                    {"shortcuts": [(hotkey._token, {})]},
                ]
            )
            with mock.patch(
                "usta.core.platform.linux.global_shortcuts.MessageBus",
                return_value=hotkey._bus,
            ):
                await hotkey._connect_and_bind()

            _, signature, body, _ = hotkey._portal_request.await_args_list[1].args
            self.assertIsInstance(body[1][0], list)
            Message(
                path="/org/freedesktop/portal/desktop",
                member="BindShortcuts",
                signature=signature,
                body=body,
            )

        asyncio.run(scenario())

    def test_portal_activation_calls_the_matching_hotkey(self):
        from dbus_next.message import Message, MessageType
        from usta.core.platform.linux.global_shortcuts import (
            SHORTCUTS_INTERFACE,
            WaylandGlobalHotkey,
        )

        callback = mock.Mock()
        hotkey = WaylandGlobalHotkey("<shift>+<alt>+t", callback)
        hotkey._session_handle = "/org/freedesktop/portal/desktop/session/usta"
        hotkey._token = "shortcut_id"
        message = Message(
            message_type=MessageType.SIGNAL,
            path="/org/freedesktop/portal/desktop",
            interface=SHORTCUTS_INTERFACE,
            member="Activated",
            body=[hotkey._session_handle, hotkey._token, 1, {}],
        )

        self.assertTrue(hotkey._on_message(message))
        callback.assert_called_once_with()

    def test_retries_keyboard_backend_and_logs_the_import_failure(self):
        backend = mock.Mock()
        backend.HotKey.parse.return_value = {"ctrl", "x"}
        hotkey = GlobalHotkey("<ctrl>+x", lambda: None)
        with (
            mock.patch("usta.core.shortcut.keyboard", None),
            mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": "x11"}),
            mock.patch(
                "usta.core.shortcut._load_keyboard",
                side_effect=[ImportError("failed to acquire X connection"), backend],
                create=True,
            ) as load_keyboard,
        ):
            with self.assertLogs("usta.core.shortcut", level="WARNING") as logs:
                self.assertFalse(hotkey.start())
            self.assertIn("failed to acquire X connection", logs.output[0])
            self.assertTrue(hotkey.start())
        self.assertEqual(load_keyboard.call_count, 2)

    def test_linux_and_windows_keep_the_existing_pynput_listener(self):
        for platform in ("linux", "win32"):
            with self.subTest(platform=platform):
                backend = mock.Mock()
                backend.HotKey.parse.return_value = {"ctrl", "x"}
                with (
                    mock.patch("usta.core.shortcut.sys.platform", platform),
                    mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": "x11"}),
                    mock.patch("usta.core.shortcut.keyboard", backend),
                    mock.patch.dict(
                        sys.modules,
                        {
                            "usta.core.platform.macos.hotkey_listener": None,
                        },
                    ),
                ):
                    hotkey = GlobalHotkey("<ctrl>+x", lambda: None)
                    self.assertTrue(hotkey.start())
                    backend.Listener.assert_called_once_with(
                        on_press=hotkey._on_press,
                        on_release=hotkey._on_release,
                    )
                    listener = backend.Listener.return_value
                    listener.start.assert_called_once()
                    hotkey.stop()
                    listener.stop.assert_called_once()


@unittest.skipUnless(
    os.environ.get("USTA_NATIVE_TESTS") == "1"
    and sys.platform == "darwin"
    and keyboard is not None,
    "Requires macOS pynput backend",
)
class MacOSHotkeyThreadTests(unittest.TestCase):
    def test_rebinding_reads_keyboard_layout_on_main_thread_only(self):
        layout_threads = []
        listener_threads = []
        contexts = []

        @contextlib.contextmanager
        def keyboard_layout():
            layout_threads.append(threading.current_thread())
            yield (40, b"copied keyboard layout")

        def listen(listener):
            listener_threads.append(threading.current_thread())
            contexts.append(listener._context)
            listener._mark_ready()

        # Substitute OS calls, leaving actual listener construction/threading intact.
        with (
            mock.patch("pynput.keyboard._darwin.keycode_context", keyboard_layout),
            mock.patch("pynput._util.darwin.keycode_context", keyboard_layout),
            mock.patch("pynput._util.darwin.ListenerMixin._run", listen),
            mock.patch(
                "usta.core.platform.macos.hotkey_listener.has_accessibility_permission",
                return_value=True,
            ),
        ):
            for combination in ("<shift>+<alt>+m", "<ctrl>+<alt>+x", "<cmd>+<shift>+k"):
                hotkey = GlobalHotkey(combination, lambda: None)
                self.assertTrue(hotkey.start())
                hotkey._listener.join(timeout=2)
                hotkey.stop()
        self.assertEqual(layout_threads, [threading.main_thread()] * 3)
        self.assertEqual(len(listener_threads), 3)
        self.assertTrue(all(thread is not threading.main_thread() for thread in listener_threads))
        self.assertEqual(contexts, [(40, b"copied keyboard layout")] * 3)

    def test_off_main_thread_registration_fails_safely(self):
        result = []
        hotkey = GlobalHotkey("<ctrl>+x", lambda: None)
        with mock.patch("pynput._util.darwin.keycode_context") as layout:
            with self.assertLogs("usta.core.shortcut", level="ERROR"):
                thread = threading.Thread(target=lambda: result.append(hotkey.start()))
                thread.start()
                thread.join(timeout=2)
            layout.assert_not_called()
        self.assertEqual(result, [False])
        self.assertIsNone(hotkey._listener)


class MacOSPermissionTests(unittest.TestCase):
    def test_missing_accessibility_warns_once_without_blocking_event_taps(self):
        import types

        import usta.core.shortcut as shortcut

        module = types.ModuleType("usta.core.platform.macos.hotkey_listener")
        module.MainThreadLayoutListener = mock.Mock()
        module.has_accessibility_permission = mock.Mock(return_value=False)
        with (
            mock.patch.object(shortcut.sys, "platform", "darwin"),
            mock.patch.object(
                shortcut,
                "keyboard",
                mock.Mock(HotKey=mock.Mock(parse=mock.Mock(return_value={"ctrl", "x"}))),
            ),
            mock.patch.object(shortcut, "_permission_warning_emitted", False, create=True),
            mock.patch.dict(sys.modules, {"usta.core.platform.macos.hotkey_listener": module}),
        ):
            with self.assertLogs("usta.core.shortcut", level="WARNING") as logs:
                self.assertTrue(GlobalHotkey("<ctrl>+x", lambda: None).start())
                self.assertTrue(GlobalHotkey("<ctrl>+y", lambda: None).start())
            self.assertEqual(len(logs.output), 1)
            self.assertIn("Accessibility", logs.output[0])
            self.assertEqual(module.MainThreadLayoutListener.call_count, 2)

    def test_new_listener_rechecks_permission_after_grant(self):
        import types

        import usta.core.shortcut as shortcut

        module = types.ModuleType("usta.core.platform.macos.hotkey_listener")
        module.MainThreadLayoutListener = mock.Mock()
        module.has_accessibility_permission = mock.Mock(side_effect=[False, True])
        with (
            mock.patch.object(shortcut.sys, "platform", "darwin"),
            mock.patch.object(
                shortcut,
                "keyboard",
                mock.Mock(HotKey=mock.Mock(parse=mock.Mock(return_value={"ctrl", "x"}))),
            ),
            mock.patch.object(shortcut, "_permission_warning_emitted", True, create=True),
            mock.patch.dict(sys.modules, {"usta.core.platform.macos.hotkey_listener": module}),
        ):
            hotkey = GlobalHotkey("<ctrl>+x", lambda: None)
            self.assertTrue(hotkey.start())
            hotkey.stop()
            self.assertTrue(hotkey.start())
            self.assertEqual(module.MainThreadLayoutListener.return_value.start.call_count, 2)
            hotkey.stop()
