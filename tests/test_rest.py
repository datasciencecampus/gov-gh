"""Tests for the GitHub REST API client."""

from unittest.mock import MagicMock

import pytest

from gov_gh.auth import GitHubAuth
from gov_gh.rest import RESTClient


@pytest.fixture()
def session() -> MagicMock:
    """Return a requests-compatible session mock."""
    return MagicMock()


def test_request_sends_authenticated_relative_request(session: MagicMock) -> None:
    """REST requests should target GitHub and return decoded JSON data."""
    response = session.request.return_value
    response.status_code = 200
    response.content = b'{"login": "ons"}'
    response.json.return_value = {"login": "ons"}
    client = RESTClient(GitHubAuth.from_token("token"), session=session)

    result = client.request("get", "/orgs/ons", params={"page": 1})

    assert result == {"login": "ons"}
    session.headers.update.assert_called_once()
    session.request.assert_called_once_with(
        "GET",
        "https://api.github.com/orgs/ons",
        params={"page": 1},
        json=None,
        timeout=30,
    )
    response.raise_for_status.assert_called_once_with()


def test_request_rejects_absolute_url(session: MagicMock) -> None:
    """Absolute URLs should be rejected to keep credentials scoped to GitHub."""
    client = RESTClient(GitHubAuth.from_token("token"), session=session)

    with pytest.raises(ValueError, match="must be relative"):
        client.request("GET", "https://example.com/data")

    session.request.assert_not_called()


def test_close_closes_session(session: MagicMock) -> None:
    """Closing the REST client should release its HTTP session."""
    RESTClient(GitHubAuth.from_token("token"), session=session).close()

    session.close.assert_called_once_with()
