"""Pytest configuration and runtime compatibility patches."""
from __future__ import annotations

"""Pytest configuration and compatibility shims for the test suite."""

import inspect
import typing


def _ensure_forward_ref_compatibility() -> None:
    forward_ref = getattr(typing, "ForwardRef", None)
    if forward_ref is None:
        return
    original = getattr(forward_ref, "_evaluate", None)
    if original is None:
        return
    signature = inspect.signature(original)
    keyword_only = [param for param in signature.parameters.values() if param.kind is inspect.Parameter.KEYWORD_ONLY]
    if not keyword_only:
        return

    def _patched(self, globalns, localns, *positional, **kwargs):  # type: ignore[override]
        positional = list(positional)
        if "recursive_guard" not in kwargs:
            if positional:
                kwargs["recursive_guard"] = positional.pop()
            else:
                kwargs["recursive_guard"] = set()
        return original(self, globalns, localns, *positional, **kwargs)

    setattr(forward_ref, "_evaluate", _patched)


_ensure_forward_ref_compatibility()
