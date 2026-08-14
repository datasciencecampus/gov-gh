"""Tests for package version metadata."""

from gov_gh import __version__


def test_version_is_string() -> None:
    """Verify the exposed package version is a string."""
    assert isinstance(__version__, str)
