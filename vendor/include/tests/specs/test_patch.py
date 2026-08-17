"""Tests for taiyi-include patch module.

Covers all 6 patch operations from upstream
``@deepseek-ai/cordis-plugin-include``:

1. ``insert`` top-level append + immediate indexing
2. ``insert`` with id target → push into target.config (group)
3. ``id + config`` replacement (shallow)
4. ``id + name`` mismatch → warn-skip
5. ``id + disabled: !!js <bool>`` (regular field assignment)
6. Other field assignment
Plus detach guarantee: result must be detached from input.
"""

from __future__ import annotations

from typing import Any

from include.patch import PatchOptions, apply_entry_patches

# ---------------------------------------------------------------------------
# Detach guarantee
# ---------------------------------------------------------------------------


class TestDetach:
    """apply_entry_patches must always return a detached entry list."""

    def test_no_patches_returns_detached(self) -> None:
        data: list[dict[str, Any]] = [{"id": "a", "name": "A"}]
        result = apply_entry_patches(data, [], lambda *a: None)
        assert result == [{"id": "a", "name": "A"}]
        # Mutating the result must not affect input
        result.append({"id": "b"})
        assert len(data) == 1

    def test_undefined_patches_returns_detached(self) -> None:
        data: list[dict[str, Any]] = [{"id": "a"}]
        result = apply_entry_patches(data, None, lambda *a: None)
        assert result == [{"id": "a"}]
        result.clear()
        assert data == [{"id": "a"}]

    def test_mutating_result_does_not_change_input(self) -> None:
        original = {"id": "a", "name": "A", "config": {"x": 1}}
        data: list[dict[str, Any]] = [original]
        result = apply_entry_patches(
            data,
            [PatchOptions(id="a", name="A2")],
            lambda *a: None,
        )
        result[0]["name"] = "mutated"
        assert original["name"] == "A"


# ---------------------------------------------------------------------------
# Operation 1: insert (top-level append + index immediately)
# ---------------------------------------------------------------------------


class TestInsertTopLevel:
    """``insert`` without an id appends to top-level data."""

    def test_appends_inserted_entries(self) -> None:
        data: list[dict[str, Any]] = [{"id": "existing"}]
        inserted = [{"id": "a"}, {"id": "b"}]
        result = apply_entry_patches(
            data,
            [PatchOptions(insert=inserted)],
            lambda *a: None,
        )
        assert [e["id"] for e in result] == ["existing", "a", "b"]

    def test_insert_indexes_for_later_patch(self) -> None:
        """An insert in one patch must be targetable by a later patch in
        the same list — patch lists compose one layer per source."""
        data: list[dict[str, Any]] = []
        result = apply_entry_patches(
            data,
            [
                PatchOptions(insert=[{"id": "a", "name": "first"}]),
                PatchOptions(id="a", disabled=True),
            ],
            lambda *a: None,
        )
        assert result[0]["disabled"] is True

    def test_insert_indexes_for_later_insert(self) -> None:
        data: list[dict[str, Any]] = []
        result = apply_entry_patches(
            data,
            [
                PatchOptions(insert=[{"id": "group1", "group": True, "config": []}]),
                PatchOptions(id="group1", insert=[{"id": "child"}]),
            ],
            lambda *a: None,
        )
        assert result[0]["config"] == [{"id": "child"}]

    def test_empty_insert_is_noop(self) -> None:
        data: list[dict[str, Any]] = [{"id": "a"}]
        result = apply_entry_patches(
            data,
            [PatchOptions(insert=[])],
            lambda *a: None,
        )
        assert result == [{"id": "a"}]


# ---------------------------------------------------------------------------
# Operation 2: insert with id → push into target.config (group)
# ---------------------------------------------------------------------------


class TestInsertIntoGroup:
    """``insert`` with id targets a group entry and pushes into its config."""

    def test_pushes_into_group_config(self) -> None:
        data: list[dict[str, Any]] = [
            {"id": "g", "group": True, "config": [{"id": "child1"}]},
        ]
        result = apply_entry_patches(
            data,
            [PatchOptions(id="g", insert=[{"id": "child2"}, {"id": "child3"}])],
            lambda *a: None,
        )
        group = result[0]
        assert group["config"] == [{"id": "child1"}, {"id": "child2"}, {"id": "child3"}]

    def test_initializes_config_array_if_missing(self) -> None:
        data: list[dict[str, Any]] = [
            {"id": "g", "group": True},
        ]
        result = apply_entry_patches(
            data,
            [PatchOptions(id="g", insert=[{"id": "child"}])],
            lambda *a: None,
        )
        group = result[0]
        assert group["config"] == [{"id": "child"}]

    def test_initializes_config_array_when_non_array(self) -> None:
        """If group.config is not an array, reset to array and push."""
        data: list[dict[str, Any]] = [
            {"id": "g", "group": True, "config": {"nested": "dict"}},
        ]
        result = apply_entry_patches(
            data,
            [PatchOptions(id="g", insert=[{"id": "child"}])],
            lambda *a: None,
        )
        group = result[0]
        assert group["config"] == [{"id": "child"}]

    def test_insert_warns_when_target_missing(self) -> None:
        data: list[dict[str, Any]] = []
        warnings: list[str] = []

        def warn(message: str, *args: Any) -> None:
            formatted = message
            for arg in args:
                formatted = formatted.replace("%C", f"<<{arg}>>", 1)
            warnings.append(formatted)

        apply_entry_patches(
            data,
            [PatchOptions(id="missing", insert=[{"id": "child"}])],
            warn,
        )
        assert warnings == ["patch insert: entry <<missing>> not found"]

    def test_insert_warns_when_target_not_group(self) -> None:
        data: list[dict[str, Any]] = [{"id": "a", "name": "A"}]
        warnings: list[str] = []

        def warn(message: str, *args: Any) -> None:
            formatted = message
            for arg in args:
                formatted = formatted.replace("%C", f"<<{arg}>>", 1)
            warnings.append(formatted)

        apply_entry_patches(
            data,
            [PatchOptions(id="a", insert=[{"id": "child"}])],
            warn,
        )
        assert warnings == ["patch insert: entry <<a>> is not a group"]


# ---------------------------------------------------------------------------
# Operation 3: id + config replacement (shallow)
# ---------------------------------------------------------------------------


class TestConfigReplacement:
    """``id + config`` replaces (not deep-merges) the config field."""

    def test_replaces_config_shallow(self) -> None:
        data: list[dict[str, Any]] = [
            {"id": "a", "config": {"old": 1, "nested": {"x": 1}}},
        ]
        result = apply_entry_patches(
            data,
            [PatchOptions(id="a", config={"new": 2})],
            lambda *a: None,
        )
        # Whole replacement, not deep-merge
        assert result[0]["config"] == {"new": 2}

    def test_replaces_with_none(self) -> None:
        data: list[dict[str, Any]] = [{"id": "a", "config": {"k": 1}}]
        result = apply_entry_patches(
            data,
            [PatchOptions(id="a", config=None)],
            lambda *a: None,
        )
        assert result[0]["config"] is None

    def test_replaces_with_complex_object(self) -> None:
        data: list[dict[str, Any]] = [{"id": "a", "config": {"old": 1}}]
        new_cfg = {"deep": [{"x": 1}, {"y": 2}], "flag": True}
        result = apply_entry_patches(
            data,
            [PatchOptions(id="a", config=new_cfg)],
            lambda *a: None,
        )
        assert result[0]["config"] is new_cfg


# ---------------------------------------------------------------------------
# Operation 4: id + name mismatch → warn-skip
# ---------------------------------------------------------------------------


class TestNameMismatch:
    """If ``name`` is provided and does not match the target, warn + skip."""

    def test_matching_name_no_warning(self) -> None:
        data: list[dict[str, Any]] = [{"id": "a", "name": "A"}]
        warnings: list[str] = []

        def warn(message: str, *args: Any) -> None:
            warnings.append(message)

        result = apply_entry_patches(
            data,
            [PatchOptions(id="a", name="A", config={"k": 1})],
            warn,
        )
        assert warnings == []
        assert result[0]["config"] == {"k": 1}

    def test_mismatching_name_warns_and_skips(self) -> None:
        data: list[dict[str, Any]] = [{"id": "a", "name": "A"}]
        warnings: list[str] = []

        def warn(message: str, *args: Any) -> None:
            formatted = message
            for arg in args:
                formatted = formatted.replace("%C", repr(arg), 1)
            warnings.append(formatted)

        result = apply_entry_patches(
            data,
            [PatchOptions(id="a", name="WRONG", config={"k": 1})],
            warn,
        )
        # The message template + arg formatting is upstream; warn-skip means
        # the patch is ignored entirely.
        assert len(warnings) == 1
        assert "name mismatch" in warnings[0]
        assert "a" in warnings[0]
        assert "WRONG" in warnings[0]
        # config was NOT applied
        assert result[0].get("config") is None


# ---------------------------------------------------------------------------
# Operation 5: id + disabled (regular field assignment)
# ---------------------------------------------------------------------------


class TestDisabledAssignment:
    """``id + disabled: !!js <bool>`` is just a regular field assignment."""

    def test_disabled_js_expr(self) -> None:
        data: list[dict[str, Any]] = [{"id": "a"}]
        disabled = {"__jsExpr": "process.platform === 'win32'"}
        result = apply_entry_patches(
            data,
            [PatchOptions(id="a", disabled=disabled)],
            lambda *a: None,
        )
        assert result[0]["disabled"] == disabled

    def test_disabled_true(self) -> None:
        data: list[dict[str, Any]] = [{"id": "a", "disabled": False}]
        result = apply_entry_patches(
            data,
            [PatchOptions(id="a", disabled=True)],
            lambda *a: None,
        )
        assert result[0]["disabled"] is True

    def test_disabled_none(self) -> None:
        data: list[dict[str, Any]] = [{"id": "a", "disabled": True}]
        result = apply_entry_patches(
            data,
            [PatchOptions(id="a", disabled=None)],
            lambda *a: None,
        )
        assert result[0]["disabled"] is None


# ---------------------------------------------------------------------------
# Operation 6: other field assignment
# ---------------------------------------------------------------------------


class TestOtherFieldAssignment:
    """Other fields like ``inject``, ``intercept``, ``isolate`` are direct assigns."""

    def test_inject_assignment(self) -> None:
        data: list[dict[str, Any]] = [{"id": "a"}]
        result = apply_entry_patches(
            data,
            [PatchOptions(id="a", inject=["b", "c"])],
            lambda *a: None,
        )
        assert result[0]["inject"] == ["b", "c"]

    def test_intercept_assignment(self) -> None:
        data: list[dict[str, Any]] = [{"id": "a"}]
        result = apply_entry_patches(
            data,
            [PatchOptions(id="a", intercept={"foo": "bar"})],
            lambda *a: None,
        )
        assert result[0]["intercept"] == {"foo": "bar"}

    def test_isolate_assignment(self) -> None:
        data: list[dict[str, Any]] = [{"id": "a"}]
        result = apply_entry_patches(
            data,
            [PatchOptions(id="a", isolate=True)],
            lambda *a: None,
        )
        assert result[0]["isolate"] is True

    def test_group_field_assignment(self) -> None:
        data: list[dict[str, Any]] = [{"id": "a"}]
        result = apply_entry_patches(
            data,
            [PatchOptions(id="a", group=True)],
            lambda *a: None,
        )
        assert result[0]["group"] is True

    def test_id_field_is_skipped(self) -> None:
        """``id`` is reserved — the field should not be reassigned via the
        overrides loop (it's destructured off the patch first)."""
        data: list[dict[str, Any]] = [{"id": "a", "name": "A"}]
        # Patch the same id; the patch's ``id`` field targets, but the
        # overrides loop skips any extra ``id`` keys.
        result = apply_entry_patches(
            data,
            [PatchOptions(id="a")],
            lambda *a: None,
        )
        assert result[0]["id"] == "a"

    def test_arbitrary_extra_field(self) -> None:
        data: list[dict[str, Any]] = [{"id": "a"}]
        result = apply_entry_patches(
            data,
            [PatchOptions(id="a", custom_attr={"x": 1})],  # type: ignore[typeddict-unknown-key]
            lambda *a: None,
        )
        assert result[0]["custom_attr"] == {"x": 1}


# ---------------------------------------------------------------------------
# Validation / guard behaviors
# ---------------------------------------------------------------------------


class TestWarnings:
    """Patch warnings route through the provided warn sink."""

    def test_no_id_warns(self) -> None:
        data: list[dict[str, Any]] = []
        warnings: list[str] = []

        def warn(message: str, *args: Any) -> None:
            warnings.append(message)

        result = apply_entry_patches(
            data,
            [PatchOptions(config={"k": 1})],  # no id, not insert
            warn,
        )
        assert warnings == ["patch: id is required for non-insert patches"]
        assert result == []

    def test_missing_id_warns(self) -> None:
        data: list[dict[str, Any]] = []
        warnings: list[str] = []

        def warn(message: str, *args: Any) -> None:
            formatted = message
            for arg in args:
                formatted = formatted.replace("%C", repr(arg), 1)
            warnings.append(formatted)

        apply_entry_patches(
            data,
            [PatchOptions(id="ghost", config={"k": 1})],
            warn,
        )
        assert len(warnings) == 1
        assert "ghost" in warnings[0]
        assert "not found" in warnings[0]

    def test_default_warn_silent(self) -> None:
        """No warn sink should not crash (default no-op)."""
        # apply_entry_patches requires warn, so we just pass a no-op.
        data: list[dict[str, Any]] = []
        result = apply_entry_patches(
            data,
            [PatchOptions(id="missing", config={"k": 1})],
            lambda *a: None,
        )
        assert result == []

    def test_warn_receives_args(self) -> None:
        """Warn gets interpolated args for ``%C`` codes (caller responsibility)."""
        data: list[dict[str, Any]] = []
        captured: list[tuple[str, tuple[Any, ...]]] = []

        def warn(message: str, *args: Any) -> None:
            captured.append((message, args))

        apply_entry_patches(
            data,
            [PatchOptions(id="x")],
            warn,
        )
        assert captured and captured[0][0] == "patch: entry %C not found"
        assert captured[0][1] == ("x",)


# ---------------------------------------------------------------------------
# Compose order
# ---------------------------------------------------------------------------


class TestComposeOrder:
    """Patches apply in declared order; later patches see earlier inserts."""

    def test_later_patch_can_target_earlier_insert(self) -> None:
        data: list[dict[str, Any]] = []
        result = apply_entry_patches(
            data,
            [
                PatchOptions(insert=[{"id": "x", "name": "X"}]),
                PatchOptions(id="x", disabled=True),
            ],
            lambda *a: None,
        )
        assert result[0]["disabled"] is True

    def test_insert_then_insert_into_group(self) -> None:
        data: list[dict[str, Any]] = []
        result = apply_entry_patches(
            data,
            [
                PatchOptions(
                    insert=[
                        {
                            "id": "g",
                            "group": True,
                            "config": [{"id": "c1"}],
                        }
                    ]
                ),
                PatchOptions(id="g", insert=[{"id": "c2"}]),
            ],
            lambda *a: None,
        )
        assert result[0]["config"] == [{"id": "c1"}, {"id": "c2"}]

    def test_patch_id_then_later_insert_under_it(self) -> None:
        """A patch can both configure a pre-existing entry and inject under it."""
        data: list[dict[str, Any]] = [
            {"id": "g", "group": True, "config": [{"id": "c1"}]},
        ]
        result = apply_entry_patches(
            data,
            [
                PatchOptions(id="g", disabled=False),
                PatchOptions(id="g", insert=[{"id": "c2"}]),
            ],
            lambda *a: None,
        )
        assert result[0]["disabled"] is False
        assert result[0]["config"] == [{"id": "c1"}, {"id": "c2"}]


# ---------------------------------------------------------------------------
# EntryOptions Type
# ---------------------------------------------------------------------------


class TestPatchOptionsShape:
    """PatchOptions is a TypedDict with optional fields."""

    def test_empty_patch_options(self) -> None:
        # Should be constructible from a plain dict
        opts: PatchOptions = {}  # type: ignore[typeddict-empty]
        data: list[dict[str, Any]] = [{"id": "a"}]
        result = apply_entry_patches(data, [opts], lambda *a: None)
        assert result == [{"id": "a"}]


# ---------------------------------------------------------------------------
# Edge case: nested rebuild_index iteration
# ---------------------------------------------------------------------------


class TestNestedGroupIndex:
    """``apply_entry_patches`` recurses into nested group configs."""

    def test_nested_group_reindexed(self) -> None:
        data: list[dict[str, Any]] = [
            {
                "id": "outer",
                "group": True,
                "config": [
                    {"id": "inner", "group": True, "config": [{"id": "leaf"}]},
                ],
            },
        ]
        result = apply_entry_patches(
            data,
            [PatchOptions(id="leaf", disabled=True)],
            lambda *a: None,
        )
        leaf = result[0]["config"][0]["config"][0]
        assert leaf["disabled"] is True

    def test_group_non_list_config(self) -> None:
        """A ``group: true`` entry whose nested ``config`` is not a list
        still works (the index just doesn't recurse into it)."""
        data: list[dict[str, Any]] = [
            {
                "id": "outer",
                "group": True,
                "config": [
                    {"id": "broken", "group": True, "config": {"not": "a list"}},
                ],
            },
        ]
        result = apply_entry_patches(
            data,
            [PatchOptions(id="outer", disabled=True)],
            lambda *a: None,
        )
        assert result[0]["disabled"] is True

    def test_rebuild_index_outer_loop_exit(self) -> None:
        """An entry without ``id`` skips index insertion but the outer
        for-loop still iterates over remaining entries."""
        data: list[dict[str, Any]] = [
            {"name": "no-id"},
            {"id": "has-id"},
        ]
        result = apply_entry_patches(
            data,
            [PatchOptions(id="has-id", disabled=True)],
            lambda *a: None,
        )
        # The no-id entry is left alone; the has-id entry is patched.
        assert result[0].get("disabled") is None
        assert result[1]["disabled"] is True


__all__: list[str] = []
