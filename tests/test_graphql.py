"""Tests for the GitHub GraphQL API client."""

from unittest.mock import MagicMock, patch

import pytest

from gov_gh.auth import GitHubAuth
from gov_gh.exceptions import GraphQLResponseError
from gov_gh.graphql import GraphQLClient


@pytest.fixture()
def gql_client() -> MagicMock:
    """Return a gql-compatible client mock."""
    return MagicMock()


def test_execute_compiles_and_sends_query(gql_client: MagicMock) -> None:
    """GraphQL execution should compile a document and pass its variables."""
    gql_client.execute.return_value = {"viewer": {"login": "octocat"}}
    client = GraphQLClient(GitHubAuth.from_token("token"), client=gql_client)

    with patch("gov_gh.graphql.gql", return_value="document"):
        result = client.execute("query Viewer { viewer { login } }", {"first": 1})

    assert result == {"viewer": {"login": "octocat"}}
    gql_client.execute.assert_called_once_with("document", variable_values={"first": 1})


def test_paginate_yields_filtered_transformed_items(
    gql_client: MagicMock,
) -> None:
    """Pagination should follow cursors and transform selected nodes."""
    pages = [
        {
            "organization": {
                "repositories": {
                    "nodes": [{"name": "keep"}, {"name": "drop"}],
                    "pageInfo": {"hasNextPage": True, "endCursor": "next"},
                }
            }
        },
        {
            "organization": {
                "repositories": {
                    "nodes": [{"name": "keep-two"}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        },
    ]
    client = GraphQLClient(GitHubAuth.from_token("token"), client=gql_client)

    with patch.object(client, "execute", side_effect=pages) as mock_execute:
        result = list(
            client.paginate(
                "query",
                {"login": "ons"},
                ["organization", "repositories"],
                transform=lambda item: item["name"].upper(),
                predicate=lambda item: item["name"].startswith("keep"),
            )
        )

    assert result == ["KEEP", "KEEP-TWO"]
    assert mock_execute.call_args_list[0].args[1]["cursor"] is None
    assert mock_execute.call_args_list[1].args[1]["cursor"] == "next"


def test_paginate_requires_cursor_when_another_page_exists(
    gql_client: MagicMock,
) -> None:
    """A next page without an end cursor should raise a response error."""
    page = {
        "connection": {
            "nodes": [],
            "pageInfo": {"hasNextPage": True, "endCursor": None},
        }
    }
    client = GraphQLClient(GitHubAuth.from_token("token"), client=gql_client)

    with (
        patch.object(client, "execute", return_value=page),
        pytest.raises(GraphQLResponseError, match="endCursor"),
    ):
        list(client.paginate("query", {}, ["connection"]))
