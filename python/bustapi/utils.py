"""
Utility classes and functions for BustAPI.
"""

import asyncio
import threading
from typing import Any, Callable, Coroutine, Optional, TypeVar

T = TypeVar("T")


class LocalProxy:
    """
    A proxy to a local object, similar to werkzeug.local.LocalProxy.
    Forwards operations to the object returned by the bound function.
    """

    __slots__ = ("_local", "__wrapped__")

    def __init__(self, local: Callable[[], Any]):
        object.__setattr__(self, "_local", local)

    def _get_current_object(self) -> Any:
        """Get the currently bound object."""
        return object.__getattribute__(self, "_local")()

    @property
    def __dict__(self):
        try:
            return self._get_current_object().__dict__
        except RuntimeError:
            raise AttributeError("__dict__") from None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_current_object(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._get_current_object(), name, value)

    def __delattr__(self, name: str) -> None:
        delattr(self._get_current_object(), name)

    def __repr__(self) -> str:
        try:
            obj = self._get_current_object()
        except RuntimeError:
            return "<LocalProxy unbound>"
        return repr(obj)

    def __str__(self) -> str:
        try:
            return str(self._get_current_object())
        except RuntimeError:
            return "<LocalProxy unbound>"

    def __bool__(self) -> bool:
        try:
            return bool(self._get_current_object())
        except RuntimeError:
            return False

    def __dir__(self):
        try:
            return dir(self._get_current_object())
        except RuntimeError:
            return []

    def __eq__(self, other: Any) -> bool:
        try:
            return self._get_current_object() == other
        except RuntimeError:
            return False

    def __ne__(self, other: Any) -> bool:
        try:
            return self._get_current_object() != other
        except RuntimeError:
            return True

    def __hash__(self) -> int:
        return hash(self._get_current_object())


_background_loop: Optional[asyncio.AbstractEventLoop] = None
_background_thread: Optional[threading.Thread] = None
_loop_lock = threading.Lock()


def get_event_loop() -> asyncio.AbstractEventLoop:
    """
    Get the global background event loop for BustAPI.
    Creates and starts it if it doesn't exist.
    """
    global _background_loop, _background_thread
    with _loop_lock:
        if _background_loop is None:
            _background_loop = asyncio.new_event_loop()
            _background_thread = threading.Thread(
                target=_background_loop.run_forever,
                name="BustAPI-EventLoop",
                daemon=True,
            )
            _background_thread.start()
    return _background_loop


def async_to_sync(coro: Coroutine[Any, Any, T]) -> T:
    """
    Run an async coroutine synchronously on the global background loop.

    This ensures that async operations (like ORM calls) always run on the same
    event loop regardless of which thread triggers them, avoiding common
    "loop conflict" errors.
    """
    loop = get_event_loop()

    # Avoid deadlocks if accidentally called from the loop thread itself
    if threading.current_thread() is _background_thread:
        # If we're already in the loop, we should have awaited the coro.
        # But since we're in a sync function, we can't.
        # This is an architectural error in the calling code.
        raise RuntimeError(
            "async_to_sync called from within the background event loop thread"
        )

    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()
