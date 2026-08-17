"""``include.patch`` — pure patch semantics for entry lists.

1:1 port of upstream
``~/deepseek-harness/vendor/include/src/index.ts:applyEntryPatches``. Shared
by both mounting (``Include._apply``) and offline config tooling so a dump
can never drift from what boots.

Rules (verbatim from upstream):

- ``insert`` top-level append + index immediately for later patches.
- ``insert`` with id target → push into ``target.config`` (group required).
- ``id + config`` replacement (shallow, no deep merge).
- ``id + name`` mismatch → warn-skip.
- ``id + disabled: !!js <bool>`` (and other fields) → direct field assign.
- Returns a *detached* entry list (``structuredClone`` semantics); even with
  no patches.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any, NotRequired, TypedDict

__all__ = ["PatchOptions", "apply_entry_patches"]


class PatchOptions(TypedDict, total=False):
    """One configured patch applied to the entry list.

    Mirrors upstream ``interface PatchOptions``. Every field is optional;
    the ``id`` is required for non-insert patches. ``disabled`` accepts
    ``JsExpr`` (``{ __jsExpr: str }``) as well as plain bools, matching
    the upstream ``disabled?: boolean | null`` semantics where ``!!js``
    payloads are evaluated at entry activation time.
    """

    id: NotRequired[str]
    insert: NotRequired[list[dict[str, Any]]]
    name: NotRequired[str]
    config: NotRequired[Any]
    group: NotRequired[bool | None]
    disabled: NotRequired[Any]
    inject: NotRequired[Any]
    intercept: NotRequired[Any]
    isolate: NotRequired[Any]


_Warn = Callable[..., None]


def apply_entry_patches(
    data: list[dict[str, Any]],
    patches: list[PatchOptions] | None,
    warn: _Warn,
) -> list[dict[str, Any]]:
    """Apply ``patches`` to ``data`` and return a detached entry list.

    See module docstring for the full rule set. ``warn`` receives printf-style
    messages where ``%C`` markers are formatted by the caller (matches
    upstream's ``logger.warn(message, ...args)``).
    """
    # structuredClone — return a deep copy so mutation isolation holds even
    # when no patches are supplied. Patch lists compose one layer per source
    # (each bundle layer, then the user's, then `--patch` overlays) and a
    # late apply must be able to revert a removed or changed patch.
    data = copy.deepcopy(data)
    if not patches:
        return data

    index: dict[str, dict[str, Any]] = {}

    def _rebuild_index(entries: list[dict[str, Any]]) -> None:
        for entry in entries:
            entry_id = entry.get("id")
            if entry_id:
                index[entry_id] = entry
            config = entry.get("config")
            if entry.get("group") and isinstance(config, list):
                _rebuild_index(config)

    _rebuild_index(data)

    for patch in patches:
        patch_id = patch.get("id")
        insert = patch.get("insert")
        name = patch.get("name")
        overrides = {k: v for k, v in patch.items() if k not in ("id", "insert", "name")}

        if insert:
            if patch_id:
                target = index.get(patch_id)
                if target is None:
                    warn("patch insert: entry %C not found", patch_id)
                    continue
                if not target.get("group"):
                    warn("patch insert: entry %C is not a group", patch_id)
                    continue
                if not isinstance(target.get("config"), list):
                    target["config"] = []
                target["config"].extend(insert)
            else:
                data.extend(insert)
            # Index what this patch added so a LATER patch can target it.
            _rebuild_index(insert)
            continue

        if not patch_id:
            warn("patch: id is required for non-insert patches")
            continue

        target = index.get(patch_id)
        if target is None:
            warn("patch: entry %C not found", patch_id)
            continue

        if name and name != target.get("name"):
            warn(
                "patch: name mismatch for %C (expected %C, got %C), skipping",
                patch_id,
                target.get("name"),
                name,
            )
            continue

        for key, value in overrides.items():
            target[key] = value

    return data
