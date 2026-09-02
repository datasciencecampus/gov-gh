"""Tests for the GitHub GraphQL API client."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, Field, ValidationError

from gov_gh.auth import GitHubAuth
from gov_gh.graphql import GraphQLClient
from gov_gh.models import GraphQLConnection, GraphQLVariables


class ViewerVariables(GraphQLVariables):
    """Variables accepted by the viewer test query."""

    first: int = Field(ge=1)


class Viewer(BaseModel):
    """Viewer fields returned by the test query."""

    login: str


class ViewerResult(BaseModel):
    """Validated result of the viewer test query."""

    viewer: Viewer


class Repository(BaseModel):
    """Repository fields returned by the pagination test query."""

    name: str


class RepositoryVariables(GraphQLVariables):
    """Variables accepted by the repository pagination query."""

    login: str
    cursor: str | None = None


class Organization(BaseModel):
    """Organization containing a repository connection."""

    repositories: GraphQLConnection[Repository]


class RepositoryPage(BaseModel):
    """Validated page returned by the repository pagination query."""

    organization: Organization


@pytest.fixture()
def gql_client() -> MagicMock:
    """Return a gql-compatible client mock."""
    return MagicMock()


def test_execute_serializes_variables_and_validates_result(
    gql_client: MagicMock,
) -> None:
    """Execution should send model data and return a validated result model."""
    gql_client.execute.return_value = {"viewer": {"login": "octocat"}}
    client = GraphQLClient(GitHubAuth.from_token("token"), client=gql_client)

    with patch("gov_gh.graphql.gql", return_value="document"):
        result = client.execute(
            "query Viewer { viewer { login } }",
            ViewerVariables(first=1),
            result_model=ViewerResult,
        )

    assert result == ViewerResult(viewer=Viewer(login="octocat"))
    gql_client.execute.assert_called_once_with("document", variable_values={"first": 1})


def test_execute_rejects_invalid_response(gql_client: MagicMock) -> None:
    """A response that violates the result model should fail validation."""
    gql_client.execute.return_value = {"viewer": {"name": "octocat"}}
    client = GraphQLClient(GitHubAuth.from_token("token"), client=gql_client)

    with (
        patch("gov_gh.graphql.gql", return_value="document"),
        pytest.raises(ValidationError, match="login"),
    ):
        client.execute("query", None, result_model=ViewerResult)

    gql_client.execute.assert_called_once()


def test_invalid_variables_never_reach_transport(gql_client: MagicMock) -> None:
    """Invalid outgoing variables should fail before transport execution."""
    client = GraphQLClient(GitHubAuth.from_token("token"), client=gql_client)

    with pytest.raises(ValidationError):
        variables = ViewerVariables(first=0)
        client.execute("query", variables, result_model=ViewerResult)

    gql_client.execute.assert_not_called()


def test_paginate_yields_validated_filtered_items(gql_client: MagicMock) -> None:
    """Pagination should follow cursors and yield selected repository models."""
    gql_client.execute.side_effect = [
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

    with patch("gov_gh.graphql.gql", return_value="document"):
        result = list(
            client.paginate(
                "query",
                RepositoryVariables(login="ons"),
                result_model=RepositoryPage,
                get_connection=lambda page: page.organization.repositories,
                predicate=lambda repository: repository.name.startswith("keep"),
            )
        )

    assert result == [Repository(name="keep"), Repository(name="keep-two")]
    first_variables = gql_client.execute.call_args_list[0].kwargs["variable_values"]
    second_variables = gql_client.execute.call_args_list[1].kwargs["variable_values"]
    assert first_variables["cursor"] is None
    assert second_variables["cursor"] == "next"


def test_paginate_validates_page_info(gql_client: MagicMock) -> None:
    """A next page without an end cursor should fail response validation."""
    gql_client.execute.return_value = {
        "organization": {
            "repositories": {
                "nodes": [],
                "pageInfo": {"hasNextPage": True, "endCursor": None},
            }
        }
    }
    client = GraphQLClient(GitHubAuth.from_token("token"), client=gql_client)

    with (
        patch("gov_gh.graphql.gql", return_value="document"),
        pytest.raises(ValidationError, match="endCursor"),
    ):
        list(
            client.paginate(
                "query",
                RepositoryVariables(login="ons"),
                result_model=RepositoryPage,
                get_connection=lambda page: page.organization.repositories,
            )
        )
