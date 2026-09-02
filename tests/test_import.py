"""Tests for the package's public imports."""

from gov_gh import GitHubClient, GraphQLClient, RESTClient, __version__


def test_version_is_string() -> None:
    """Verify the exposed package version is a string."""
    assert isinstance(__version__, str)


def test_public_clients_are_importable() -> None:
    """All supported client classes should be exported at package level."""
    assert GitHubClient.__name__ == "GitHubClient"
    assert GraphQLClient.__name__ == "GraphQLClient"
    assert RESTClient.__name__ == "RESTClient"
