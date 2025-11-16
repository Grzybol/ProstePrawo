"""Pytest configuration and runtime compatibility patches."""
from __future__ import annotations

"""Pytest configuration and compatibility shims for the test suite."""

import inspect
import sys
import types
import typing


def _ensure_pydantic_stubs() -> None:
    if "pydantic" not in sys.modules:  # pragma: no cover - executed in CI without dependency
        module = types.ModuleType("pydantic")

        class BaseModel:  # pragma: no cover - simple stub
            def __init__(self, **kwargs) -> None:
                for key, value in kwargs.items():
                    setattr(self, key, value)

            def dict(self, **kwargs):  # type: ignore[override]
                return self.__dict__.copy()

        def Field(default=None, **kwargs):  # pragma: no cover - simple stub
            return default

        class EmailStr(str):  # pragma: no cover - simple stub
            pass

        module.BaseModel = BaseModel
        module.Field = Field
        module.EmailStr = EmailStr
        sys.modules["pydantic"] = module

    if "pydantic_settings" not in sys.modules:  # pragma: no cover - executed in CI without dependency
        module = types.ModuleType("pydantic_settings")

        class BaseSettings:  # pragma: no cover - simple stub
            def __init__(self, **kwargs) -> None:
                for key, value in kwargs.items():
                    setattr(self, key, value)

        module.BaseSettings = BaseSettings
        sys.modules["pydantic_settings"] = module


def _ensure_openai_stub() -> None:
    try:
        import openai  # noqa: F401  # pragma: no cover - optional dependency
    except ModuleNotFoundError:  # pragma: no cover - executed in CI without openai
        module = types.ModuleType("openai")

        class AuthenticationError(Exception):
            """Fallback authentication error used in tests."""

        class _StubCompletions:  # pragma: no cover - simple stub
            def create(self, *args, **kwargs):
                raise RuntimeError("OpenAI API is not available in the test environment.")

        class OpenAI:  # pragma: no cover - simple stub
            def __init__(self, *args, **kwargs) -> None:
                self.chat = types.SimpleNamespace(completions=_StubCompletions())

        module.AuthenticationError = AuthenticationError
        module.OpenAI = OpenAI
        sys.modules["openai"] = module


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


_ensure_pydantic_stubs()
_ensure_forward_ref_compatibility()
_ensure_openai_stub()
