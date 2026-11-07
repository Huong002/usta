"""Global keyboard shortcuts through the XDG desktop portal on Wayland."""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import threading

from dbus_next import BusType, DBusError, Variant
from dbus_next.aio import MessageBus
from dbus_next.message import Message, MessageType

logger = logging.getLogger(__name__)

BUS_NAME = "org.freedesktop.portal.Desktop"
OBJECT_PATH = "/org/freedesktop/portal/desktop"
SHORTCUTS_INTERFACE = "org.freedesktop.portal.GlobalShortcuts"
REQUEST_INTERFACE = "org.freedesktop.portal.Request"
SESSION_INTERFACE = "org.freedesktop.portal.Session"
REGISTRY_INTERFACE = "org.freedesktop.host.portal.Registry"
DBUS_NAME = "org.freedesktop.DBus"
DBUS_PATH = "/org/freedesktop/DBus"
DBUS_INTERFACE = "org.freedesktop.DBus"

_MODIFIERS = {
    "ctrl": "CTRL",
    "control": "CTRL",
    "alt": "ALT",
    "shift": "SHIFT",
    "cmd": "LOGO",
    "super": "LOGO",
    "meta": "LOGO",
}
_KEY_NAMES = {
    "esc": "Escape",
    "escape": "Escape",
    "enter": "Return",
    "return": "Return",
    "space": "space",
    "tab": "Tab",
    "backspace": "BackSpace",
    "delete": "Delete",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
}


def to_portal_trigger(hotkey: str) -> str:
    """Convert pynput's ``<ctrl>+x`` syntax to the XDG shortcuts syntax."""
    parts = hotkey.split("+")
    if not parts or any(not part for part in parts):
        raise ValueError(f"Invalid hotkey: {hotkey!r}")

    result = []
    for part in parts[:-1]:
        modifier = part.strip("<>").lower()
        if modifier not in _MODIFIERS:
            raise ValueError(f"Unsupported hotkey modifier: {part!r}")
        result.append(_MODIFIERS[modifier])

    key = parts[-1].strip("<>")
    if len(key) == 1 and key.isalpha():
        key = key.lower()
    else:
        key = _KEY_NAMES.get(key.lower(), key.upper() if re.fullmatch(r"f\d+", key, re.I) else key)
    if not re.fullmatch(r"[A-Za-z0-9_]+", key):
        raise ValueError(f"Unsupported hotkey key: {key!r}")
    return "+".join([*result, key])


class WaylandGlobalHotkey:
    """One portal session and shortcut binding, serviced on a private asyncio thread."""

    def __init__(self, hotkey, callback):
        self.hotkey = hotkey
        self.callback = callback
        self._thread = None
        self._loop = None
        self._bus = None
        self._session_handle = None
        self._ready = threading.Event()
        self._startup_error = None
        self._stopping = None
        self._token = secrets.token_hex(8)

    def start(self):
        if self._thread is not None:
            return True
        self._thread = threading.Thread(
            target=self._run, name="usta-wayland-hotkey", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(10):
            logger.error("Timed out connecting to the XDG GlobalShortcuts portal.")
            self.stop()
            return False
        if self._startup_error is not None:
            logger.error("Could not initialize Wayland global shortcut: %s", self._startup_error)
            self.stop()
            return False
        return True

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stopping = asyncio.Event()
        try:
            self._loop.run_until_complete(self._connect_and_bind())
        except Exception as exc:
            self._startup_error = exc
            self._ready.set()
            logger.exception("Wayland global shortcut portal failed for %s", self.hotkey)
        finally:
            if self._bus is not None:
                self._bus.disconnect()
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.close()

    async def _connect_and_bind(self):
        self._bus = await MessageBus(bus_type=BusType.SESSION).connect()
        await self._register_app_id()
        await self._add_match(
            f"type='signal',interface='{SHORTCUTS_INTERFACE}',member='Activated'"
        )
        self._bus.add_message_handler(self._on_message)

        create_token = f"create_{self._token}"
        create_results = await self._portal_request(
            "CreateSession",
            "a{sv}",
            [{
                "session_handle_token": Variant("s", f"session_{self._token}"),
                "handle_token": Variant("s", create_token),
            }],
            create_token,
        )
        self._session_handle = create_results["session_handle"].value
        self._ready.set()

        bind_token = f"bind_{self._token}"
        bind_results = await self._portal_request(
            "BindShortcuts",
            "oa(sa{sv})sa{sv}",
            [
                self._session_handle,
                [[self._token, {
                    "description": Variant("s", "USTA shortcut"),
                    "preferred_trigger": Variant("s", to_portal_trigger(self.hotkey)),
                }]],
                "",
                {"handle_token": Variant("s", bind_token)},
            ],
            bind_token,
        )
        if not any(shortcut_id == self._token for shortcut_id, _ in bind_results.get("shortcuts", [])):
            logger.warning(
                "The desktop portal did not bind USTA shortcut %s. Review the Global Shortcuts prompt or desktop settings.",
                self.hotkey,
            )
        else:
            logger.info("Wayland global shortcut registered through desktop portal: %s", self.hotkey)
        await self._stopping.wait()

    async def _register_app_id(self):
        try:
            reply = await self._bus.call(
                Message(
                    destination=BUS_NAME,
                    path=OBJECT_PATH,
                    interface=REGISTRY_INTERFACE,
                    member="Register",
                    signature="sa{sv}",
                    body=["usta", {}],
                )
            )
        except DBusError as exc:
            if exc.type.endswith("UnknownMethod"):
                logger.debug("Host portal app registry is unavailable; using legacy portal flow.")
                return
            raise RuntimeError(
                "Could not register USTA with the desktop portal. Ensure `usta.desktop` is "
                "installed in an XDG applications directory before using Wayland hotkeys."
            ) from exc
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(
                "Could not register USTA with the desktop portal. Ensure `usta.desktop` is "
                "installed in an XDG applications directory before using Wayland hotkeys."
            )

    def _on_message(self, message):
        if (
            message.message_type == MessageType.SIGNAL
            and message.interface == SHORTCUTS_INTERFACE
            and message.member == "Activated"
            and len(message.body) >= 2
            and message.body[0] == self._session_handle
            and message.body[1] == self._token
        ):
            try:
                self.callback()
            except Exception:
                logger.exception("Wayland hotkey callback failed for %s", self.hotkey)
            return True
        return None

    async def _add_match(self, rule):
        reply = await self._bus.call(
            Message(
                destination=DBUS_NAME,
                path=DBUS_PATH,
                interface=DBUS_INTERFACE,
                member="AddMatch",
                signature="s",
                body=[rule],
            )
        )
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(reply.body[0] if reply.body else "D-Bus AddMatch failed")

    def _request_path(self, token):
        sender = self._bus.unique_name.removeprefix(":").replace(".", "_")
        return f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

    async def _portal_request(self, member, signature, body, token):
        path = self._request_path(token)
        response = self._loop.create_future()

        def handler(message):
            if (
                message.path == path
                and message.interface == REQUEST_INTERFACE
                and message.member == "Response"
            ):
                if not response.done():
                    response.set_result(message.body)
                return True
            return None

        self._bus.add_message_handler(handler)
        await self._add_match(
            f"type='signal',interface='{REQUEST_INTERFACE}',member='Response',path='{path}'"
        )
        try:
            reply = await self._bus.call(
                Message(
                    destination=BUS_NAME,
                    path=OBJECT_PATH,
                    interface=SHORTCUTS_INTERFACE,
                    member=member,
                    signature=signature,
                    body=body,
                )
            )
            if reply.message_type == MessageType.ERROR:
                raise RuntimeError(reply.body[0] if reply.body else f"{member} failed")
            if reply.body[0] != path:
                raise RuntimeError(f"Unexpected portal request path: {reply.body[0]}")
            code, results = await response
            if code != 0:
                raise RuntimeError(f"Portal rejected {member} (response {code})")
            return results
        finally:
            self._bus.remove_message_handler(handler)

    def stop(self):
        if self._thread is None:
            return
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._stopping.set)
            if self._session_handle is not None:
                asyncio.run_coroutine_threadsafe(self._close_session(), self._loop)
            self._thread.join(timeout=3)
            if self._thread.is_alive():
                self._loop.call_soon_threadsafe(self._loop.stop)
                self._thread.join(timeout=1)
        self._thread = None

    async def _close_session(self):
        try:
            await self._bus.call(
                Message(
                    destination=BUS_NAME,
                    path=self._session_handle,
                    interface=SESSION_INTERFACE,
                    member="Close",
                )
            )
        except Exception:
            logger.debug("Could not close Wayland global shortcut session", exc_info=True)
