"""Typed coercion helpers for parsing untyped JSON (``dict[str, object]``) into the
config / ledger dataclasses under mypy --strict, without scattering ``type: ignore``.

Each helper narrows an ``object`` to a concrete type and fails loud on a wrong type, so
a malformed field (e.g. a string where a number belongs) is a clear error at the
boundary rather than a silent coercion or an opaque overload complaint.
"""

from __future__ import annotations

from collections.abc import Mapping


def as_int(value: object, field: str) -> int:
    # bool is an int subclass; reject it so a JSON ``true`` can't become ``1`` silently.
    if isinstance(value, bool):
        raise TypeError(f"{field}: expected an int, got bool {value!r}")
    if isinstance(value, (int, float, str)):
        return int(value)
    raise TypeError(f"{field}: expected an int-like value, got {type(value).__name__}")


def as_float(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{field}: expected a float, got bool {value!r}")
    if isinstance(value, (int, float, str)):
        return float(value)
    raise TypeError(f"{field}: expected a float-like value, got {type(value).__name__}")


def as_str(value: object, field: str) -> str:
    if isinstance(value, str):
        return value
    raise TypeError(f"{field}: expected a string, got {type(value).__name__}")


def as_bool(value: object, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise TypeError(f"{field}: expected a bool, got {type(value).__name__}")


def as_mapping(value: object, field: str) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    raise TypeError(f"{field}: expected an object, got {type(value).__name__}")


def opt_int(value: object, field: str) -> int | None:
    return None if value is None else as_int(value, field)


def opt_float(value: object, field: str) -> float | None:
    return None if value is None else as_float(value, field)
