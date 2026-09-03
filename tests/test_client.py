"""Tests for the top-level GitHub API client."""

from unittest.mock import patch

from gov_gh.client import GitHubClient


def test_client_constructs_graphql_client() -> None:
    """The facade should initialise a GraphQL client with configured retries."""
    with patch("gov_gh.client.GraphQLClient") as graphql_class:
        client = GitHubClient("token", max_retries=5)

    assert client.graphql is graphql_class.return_value
    graphql_args = graphql_class.call_args.args
    assert graphql_args[2].max_retries == 5
