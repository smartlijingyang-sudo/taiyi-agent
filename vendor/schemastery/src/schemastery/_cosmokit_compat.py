"""Inline compatibility layer for `@deepseek-ai/cosmokit` utilities.

TODO(integration): replace _cosmokit_compat with `from taiyi_cosmokit import ...` once cosmokit lands.

This module inlines the nine utility functions consumed by the schemastery
port so the package is self-contained until the cosmokit subagent delivers
the parallel `vendor/cosmokit/` Python package. The signatures mirror the
upstream TypeScript sources in `~/deepseek-harness/vendor/cosmokit/src/`
(`misc.ts`, `types.ts`).

Mapping (TS name → Python name) used throughout schemastery:

    Binary               -> Binary (namespace object)
    clone                -> clone
    deepEqual            -> deep_equal
    filterKeys           -> filter_keys
    isNullable           -> is_nullable
    isPlainObject        -> is_plain_object
    pick                 -> pick
    valueMap             -> value_map
    Dict                 -> Dict (typing alias)

Once the orchestrator swaps in the real `taiyi_cosmokit` package, the
imports in `schema.py` / `types.py` / `dsl.py` will be rewired and this
file will be deleted.
"""

from __future__ import annotations

import base64 as _base64
import re as _re
from collections.abc import Callable as _Callable
from collections.abc import Iterable as _Iterable
from collections.abc import Mapping
from typing import Any, TypeAlias, TypeVar

__all__ = [
    "Binary",
    "Dict",
    "clone",
    "deep_equal",
    "filter_keys",
    "is_nullable",
    "is_plain_object",
    "pick",
    "value_map",
]

K = TypeVar("K")
V = TypeVar("V")
U = TypeVar("U")

Dict: TypeAlias = Mapping[str, Any]


def is_nullable(value: Any) -> bool:
    """Return ``True`` when ``value`` is ``None`` (TS ``null`` or ``undefined``)."""
    return value is None


def is_plain_object(data: Any) -> bool:
    """Return ``True`` for non-array object values (TS plain-object shape)."""
    return isinstance(data, Mapping) and not isinstance(data, (str, bytes))


def _same_primitive_type(a: Any, b: Any) -> bool:
    """Both ``a`` and ``b`` are the same non-None primitive type."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b)  # bool is a subclass of int — treat separately.
    if isinstance(a, (int, float, str)) and isinstance(b, (int, float, str)):
        return type(a) is type(b)
    return False


def deep_equal(a: Any, b: Any, strict: bool = False) -> bool:
    """Deeply compare arrays, dates, regexps, buffers, and plain object fields."""
    if not strict and is_nullable(a) and is_nullable(b):
        return True  # marker: nullable short-circuit
    if a is b:
        return True
    # Primitive type mismatch => unequal.
    if _same_primitive_type(a, b) is False and (
        isinstance(a, (int, float, str, bool)) or isinstance(b, (int, float, str, bool))
    ):
        return False
    if isinstance(a, (int, float, str, bool)) or isinstance(b, (int, float, str, bool)):
        return a == b
    if a is None or b is None:
        return False

    # regex.
    if isinstance(a, _re.Pattern) and isinstance(b, _re.Pattern):
        return a.pattern == b.pattern and (a.flags == b.flags)

    # bytes / buffer.
    if isinstance(a, (bytes, bytearray, memoryview)) and isinstance(
        b, (bytes, bytearray, memoryview)
    ):
        return bytes(a) == bytes(b)

    # list / tuple.
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(deep_equal(x, y, strict) for x, y in zip(a, b, strict=False))

    # dict (order-insensitive comparison).
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        keys = set(a.keys()) | set(b.keys())
        return all(deep_equal(a.get(k), b.get(k), strict) for k in keys)

    return a == b


def clone(source: Any, refs: dict[int, Any] | None = None) -> Any:
    """Deep-clone common Python values while preserving cycles."""
    if source is None or isinstance(source, (int, float, str, bool, bytes, bytearray)):
        return source
    if refs is None:
        refs = {}
    if id(source) in refs:
        return refs[id(source)]

    if isinstance(source, _re.Pattern):
        return _re.compile(source.pattern, source.flags)

    if isinstance(source, Mapping):
        result: dict[Any, Any] = {}
        refs[id(source)] = result
        for key, value in source.items():
            result[clone(key, refs)] = clone(value, refs)
        return result

    if isinstance(source, (list, tuple)):
        result_list: list[Any] = []
        refs[id(source)] = result_list
        for value in source:
            result_list.append(clone(value, refs))
        return result_list if isinstance(source, list) else tuple(result_list)

    if isinstance(source, (set, frozenset)):
        result_set: set[Any] = set()
        refs[id(source)] = result_set
        for value in source:
            result_set.add(clone(value, refs))
        return result_set if isinstance(source, set) else frozenset(result_set)

    # Fallback: try to copy via __dict__.
    try:
        result_obj = source.__class__.__new__(source.__class__)
        refs[id(source)] = result_obj
        for key in vars(source):
            setattr(result_obj, key, clone(getattr(source, key), refs))
        return result_obj
    except Exception:
        return source


def filter_keys(
    obj: Mapping[K, V],
    predicate: _Callable[[K, V], bool],
) -> dict[K, V]:
    """Return a new dict with only the entries where ``predicate(key, value)`` is true."""
    return {k: v for k, v in obj.items() if predicate(k, v)}


def value_map(
    obj: Mapping[K, V],
    transform: _Callable[[V, K], U],
) -> dict[K, U]:
    """Map the values of ``obj`` while preserving the original keys."""
    return {k: transform(v, k) for k, v in obj.items()}


def pick(source: Mapping[K, V], keys: _Iterable[K] | None = None) -> dict[K, V]:
    """Return a shallow copy containing only ``keys`` (or all keys when ``None``)."""
    if keys is None:
        return dict(source)
    return {k: source[k] for k in keys if k in source}


# ---------------------------------------------------------------------------
# Binary helpers (subset needed for schemastery — schemastery only consumes
# `Binary.is`, `Binary.isSource`, `Binary.fromSource`, `Binary.fromBase64`,
# `Binary.fromHex`, `Binary.toBase64`, `Binary.toHex`).
# ---------------------------------------------------------------------------


class Binary:
    """Namespace mirroring ``cosmokit/types.ts::Binary``.

    Note: ``Binary.is`` and ``Binary.isSource`` are TS-only and not consumed
    by schemastery. Python cannot name an attribute ``is`` (reserved keyword),
    so only ``is_source`` is exposed. Callers should use ``Binary.is_source``
    or rely on the duck-type detection in ``Binary.from_source``.
    """

    @staticmethod
    def is_source(value: Any) -> bool:
        return isinstance(value, (bytes, bytearray, memoryview))

    @staticmethod
    def from_source(source: Any) -> bytes:
        if isinstance(source, memoryview):
            return bytes(source)
        if isinstance(source, (bytes, bytearray)):
            return bytes(source)
        raise TypeError(f"cannot convert {type(source).__name__} to bytes")

    @staticmethod
    def to_base64(source: Any) -> str:
        return _base64.b64encode(Binary.from_source(source)).decode("ascii")

    @staticmethod
    def from_base64(source: str) -> bytes:
        return _base64.b64decode(source)

    @staticmethod
    def to_hex(source: Any) -> str:
        return Binary.from_source(source).hex()

    @staticmethod
    def from_hex(source: str) -> bytes:
        if len(source) % 2:
            source = source[:-1]
        return bytes.fromhex(source)
