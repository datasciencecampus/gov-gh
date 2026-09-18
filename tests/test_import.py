"""Tests for package-level public exports."""

from gov_gh import (
    __version__,
    fetch_org_invitations,
    fetch_org_members,
    fetch_org_owners,
    fetch_org_teams,
)


def test_version_is_string() -> None:
    """Verify the exposed package version is a string."""
    assert isinstance(__version__, str)


def test_public_fetch_functions_are_exposed() -> None:
    """Verify organisation fetch helpers are available from package root."""
    assert callable(fetch_org_teams)
    assert callable(fetch_org_members)
    assert callable(fetch_org_owners)
    assert callable(fetch_org_invitations)
