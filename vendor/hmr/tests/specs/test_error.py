"""Test suite for hmr.error — HmrError type and construction."""

from __future__ import annotations

import pytest

from hmr.error import HmrError


class TestHmrError:
    """HmrError is the custom error type raised by the HMR service."""

    def test_is_exception(self):
        """HmrError subclasses Exception (and can be raised/caught normally)."""
        assert issubclass(HmrError, Exception)

    def test_construction_with_message(self):
        """The constructor accepts a message string."""
        err = HmrError("boom")
        assert str(err) == "boom"

    def test_raising_and_catching(self):
        """``raise HmrError`` is catchable as ``except HmrError``."""
        with pytest.raises(HmrError, match="bad path"):
            raise HmrError("bad path")

    def test_raising_and_catching_as_exception(self):
        """``except Exception`` catches it (sanity check)."""
        with pytest.raises(Exception, match="generic"):
            raise HmrError("generic")


__all__ = ["TestHmrError"]
