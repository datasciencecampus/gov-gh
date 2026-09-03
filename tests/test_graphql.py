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


class MutationResult(BaseModel):
    """Validated result of the mutation retry tests."""

    success: bool


REPOSITORY_QUERY = """
query Repositories {
    organization(login: "ons") {
        repositories(first: 1) {
            nodes { name }
            pageInfo { hasNextPage endCursor }
        }
    }
}
"""


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

    result = client.execute(
        "query Viewer { viewer { login } }",
        ViewerVariables(first=1),
        result_model=ViewerResult,
    )

    assert result == ViewerResult(viewer=Viewer(login="octocat"))
    call_kwargs = gql_client.execute.call_args.kwargs
    assert call_kwargs == {
        "variable_values": {"first": 1},
        "operation_name": None,
    }


def test_execute_rejects_invalid_response(gql_client: MagicMock) -> None:
    """A response that violates the result model should fail validation."""
    gql_client.execute.return_value = {"viewer": {"name": "octocat"}}
    client = GraphQLClient(GitHubAuth.from_token("token"), client=gql_client)

    with pytest.raises(ValidationError, match="login"):
        client.execute(
            "query Viewer { viewer { login } }",
            None,
            result_model=ViewerResult,
        )

    gql_client.execute.assert_called_once()


def test_invalid_variables_never_reach_transport(gql_client: MagicMock) -> None:
    """Invalid outgoing variables should fail before transport execution."""
    client = GraphQLClient(GitHubAuth.from_token("token"), client=gql_client)

    with pytest.raises(ValidationError):
        variables = ViewerVariables(first=0)
        client.execute("query", variables, result_model=ViewerResult)

    gql_client.execute.assert_not_called()


def test_query_retries_transient_failure_by_default(gql_client: MagicMock) -> None:
    """Queries should retain retry handling for transient transport failures."""
    gql_client.execute.side_effect = [
        ConnectionError("response lost"),
        {"viewer": {"login": "octocat"}},
    ]
    client = GraphQLClient(GitHubAuth.from_token("token"), client=gql_client)

    with patch("gov_gh.retry.sleep"):
        result = client.execute(
            "query Viewer { viewer { login } }",
            None,
            result_model=ViewerResult,
        )

    assert result.viewer.login == "octocat"
    assert gql_client.execute.call_count == 2


def test_mutation_does_not_retry_by_default(gql_client: MagicMock) -> None:
    """A transient mutation failure should propagate without another execution."""
    gql_client.execute.side_effect = ConnectionError("response lost")
    client = GraphQLClient(GitHubAuth.from_token("token"), client=gql_client)

    with pytest.raises(ConnectionError, match="response lost"):
        client.execute(
            "mutation CreateIssue { createIssue { success } }",
            None,
            result_model=MutationResult,
        )

    gql_client.execute.assert_called_once()


def test_mutation_retry_requires_explicit_opt_in(gql_client: MagicMock) -> None:
    """An explicitly repeatable mutation may opt in to transient retries."""
    gql_client.execute.side_effect = [
        ConnectionError("response lost"),
        {"success": True},
    ]
    client = GraphQLClient(GitHubAuth.from_token("token"), client=gql_client)

    with patch("gov_gh.retry.sleep"):
        result = client.execute(
            "mutation UpdateIssue { updateIssue { success } }",
            None,
            result_model=MutationResult,
            retry_mutations=True,
        )

    assert result.success is True
    assert gql_client.execute.call_count == 2


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

    result = list(
        client.paginate(
            REPOSITORY_QUERY,
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

    with pytest.raises(ValidationError, match="endCursor"):
        list(
            client.paginate(
                REPOSITORY_QUERY,
                RepositoryVariables(login="ons"),
                result_model=RepositoryPage,
                get_connection=lambda page: page.organization.repositories,
            )
        )
