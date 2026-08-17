"""Tests for the invariant companion barrel.

Verifies the ``invariant`` submodule re-exports the same names as the
package root, so consumers can depend on either.
"""

from __future__ import annotations

import pytest

import include as _include
import include.invariant as _invariant


class TestInvariantBarrel:
    """``include.invariant`` re-exports the package's public surface."""

    @pytest.mark.parametrize(
        "name",
        [
            "ConfigFileError",
            "Include",
            "JsExpr",
            "PatchOptions",
            "apply_entry_patches",
            "entry_list_schema",
            "evaluate",
            "is_js_expr",
        ],
    )
    def test_re_exports(self, name: str) -> None:
        assert name in _invariant.__all__, f"{name} missing from invariant.__all__"
        assert hasattr(_invariant, name)
        # And it should be the *same* object as the package root.
        assert getattr(_invariant, name) is getattr(_include, name)

    def test_invariant_is_subpackage(self) -> None:
        assert _invariant.__file__ is not None
        assert "invariant" in _invariant.__file__

    def test_invariant_no_extra_names(self) -> None:
        """Invariant must not introduce names that aren't in the root surface."""
        root_names = set(_include.__all__)
        invariant_names = set(_invariant.__all__)
        # ``entry_list_schema`` exists on both because the barrel imports it.
        assert invariant_names.issubset(root_names), invariant_names - root_names


__all__: list[str] = []
