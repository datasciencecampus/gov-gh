"""Tests for shared GitHub authentication details."""

import pytest
from pydantic import SecretStr

from gov_gh.auth import GitHubAuth


def test_auth_accepts_plain_token_and_builds_headers() -> None:
    """A plain token should be protected and added to standard GitHub headers."""
    auth = GitHubAuth.from_token("github-token")

    assert isinstance(auth.token, SecretStr)
    assert auth.headers() == {
        "Authorization": "Bearer github-token",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


@pytest.mark.parametrize("token", ["", "   ", SecretStr("")])
def test_auth_rejects_empty_token(token: str | SecretStr) -> None:
    """Empty plain and protected tokens should be rejected."""
    with pytest.raises(ValueError, match="must not be empty"):
        GitHubAuth.from_token(token)
