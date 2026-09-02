"""Tests for the top-level GitHub API client."""

from unittest.mock import patch

from gov_gh.client import GitHubClient


def test_client_constructs_both_protocol_clients() -> None:
    """The facade should initialise REST and GraphQL clients with shared objects."""
    with (
        patch("gov_gh.client.RESTClient") as rest_class,
        patch("gov_gh.client.GraphQLClient") as graphql_class,
    ):
        client = GitHubClient("token", max_retries=5)

    assert client.rest is rest_class.return_value
    assert client.graphql is graphql_class.return_value
    rest_args = rest_class.call_args.args
    graphql_args = graphql_class.call_args.args
    assert rest_args[0] is graphql_args[0]
    assert rest_args[2] is graphql_args[2]


def test_context_manager_closes_rest_client() -> None:
    """Leaving the facade context should close the REST session."""
    with (
        patch("gov_gh.client.RESTClient") as rest_class,
        patch("gov_gh.client.GraphQLClient"),
        GitHubClient("token"),
    ):
        pass

    rest_class.return_value.close.assert_called_once_with()
