"""Tests for the package's public imports."""

from gov_gh import (
    GitHubClient,
    GraphQLClient,
    GraphQLConnection,
    GraphQLPageInfo,
    GraphQLVariables,
    RESTClient,
    __version__,
)


def test_version_is_string() -> None:
    """Verify the exposed package version is a string."""
    assert isinstance(__version__, str)


def test_public_classes_are_importable() -> None:
    """All supported client and model classes should be package exports."""
    assert GitHubClient.__name__ == "GitHubClient"
    assert GraphQLClient.__name__ == "GraphQLClient"
    assert GraphQLConnection.__name__ == "GraphQLConnection"
    assert GraphQLPageInfo.__name__ == "GraphQLPageInfo"
    assert GraphQLVariables.__name__ == "GraphQLVariables"
    assert RESTClient.__name__ == "RESTClient"
