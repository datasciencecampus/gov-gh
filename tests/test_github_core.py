"""Tests for gov_gh.github_core — authentication helpers, GraphQL client creation,
retry logic, connection extraction, and cursor-based pagination."""

import logging
from http import HTTPStatus
from unittest.mock import MagicMock, call, patch

import pytest
from gql.transport.exceptions import TransportQueryError, TransportServerError
from pydantic import SecretStr

from gov_gh.exceptions import GraphQLResponseError
from gov_gh.github_core import (
    _execute_graphql_query,
    _get_auth_headers,
    _get_connection,
    _get_connection_data,
    _get_graphql_client,
    _is_retriable,
    paginate_connection,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def token() -> SecretStr:
    """A dummy PAT wrapped in SecretStr."""
    return SecretStr("ghp_testtoken123")


@pytest.fixture()
def logger() -> logging.Logger:
    """A logger that discards all output during tests."""
    log = logging.getLogger("test_github_core")
    log.addHandler(logging.NullHandler())
    return log


@pytest.fixture()
def mock_client() -> MagicMock:
    """A mock gql Client."""
    return MagicMock()


# ---------------------------------------------------------------------------
# _get_auth_headers
# ---------------------------------------------------------------------------


class TestGetAuthHeaders:
    def test_returns_authorization_header(self, token: SecretStr) -> None:
        """Headers must contain an Authorization entry with the Bearer scheme."""
        headers = _get_auth_headers(token)
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")

    def test_authorization_header_contains_token(self, token: SecretStr) -> None:
        """The Authorization header value must embed the raw token value."""
        headers = _get_auth_headers(token)
        assert "ghp_testtoken123" in headers["Authorization"]

    def test_returns_accept_header(self, token: SecretStr) -> None:
        """Headers must include the GitHub v3 Accept header."""
        headers = _get_auth_headers(token)
        assert headers.get("Accept") == "application/vnd.github+json"


# ---------------------------------------------------------------------------
# _get_graphql_client
# ---------------------------------------------------------------------------


class TestGetGraphqlClient:
    def test_returns_client_instance(self, token: SecretStr) -> None:
        """Return a gql Client without contacting the network."""
        from gql import Client

        with (
            patch("gov_gh.github_core.RequestsHTTPTransport") as mock_transport_cls,
            patch("gov_gh.github_core.Client") as mock_client_cls,
        ):
            mock_transport_cls.return_value = MagicMock()
            mock_client_cls.return_value = MagicMock(spec=Client)
            client = _get_graphql_client(token)
        assert client is mock_client_cls.return_value

    def test_transport_receives_auth_headers(self, token: SecretStr) -> None:
        """The transport must be constructed with the correct auth headers."""
        with (
            patch("gov_gh.github_core.RequestsHTTPTransport") as mock_transport_cls,
            patch("gov_gh.github_core.Client"),
        ):
            _get_graphql_client(token)
            _, kwargs = mock_transport_cls.call_args
            assert "headers" in kwargs
            assert "Authorization" in kwargs["headers"]


# ---------------------------------------------------------------------------
# _is_retriable
# ---------------------------------------------------------------------------


class TestIsRetriable:
    def test_transport_query_error_is_not_retriable(self) -> None:
        """TransportQueryError (e.g. 403 / syntax) must not be retried."""
        assert _is_retriable(TransportQueryError("forbidden")) is False

    @pytest.mark.parametrize(
        "code",
        [
            HTTPStatus.INTERNAL_SERVER_ERROR,  # 500
            HTTPStatus.BAD_GATEWAY,  # 502
            HTTPStatus.SERVICE_UNAVAILABLE,  # 503
            HTTPStatus.GATEWAY_TIMEOUT,  # 504
        ],
    )
    def test_retriable_server_error_codes(self, code: HTTPStatus) -> None:
        """5xx transient HTTP errors should be retried."""
        err = TransportServerError(f"server error {code}", code=code)
        assert _is_retriable(err) is True

    @pytest.mark.parametrize(
        "code",
        [
            HTTPStatus.BAD_REQUEST,  # 400
            HTTPStatus.FORBIDDEN,  # 403
            HTTPStatus.NOT_FOUND,  # 404
        ],
    )
    def test_non_retriable_server_error_codes(self, code: HTTPStatus) -> None:
        """Client-side HTTP errors (4xx) must not be retried."""
        err = TransportServerError(f"client error {code}", code=code)
        assert _is_retriable(err) is False

    def test_generic_exception_is_retriable(self) -> None:
        """Any other exception type (e.g. network timeout) should be retriable."""
        assert _is_retriable(ConnectionError("timeout")) is True


# ---------------------------------------------------------------------------
# _execute_graphql_query
# ---------------------------------------------------------------------------


class TestExecuteGraphqlQuery:
    def test_returns_result_on_success(
        self, mock_client: MagicMock, logger: logging.Logger
    ) -> None:
        """A successful execute call should return its result directly."""
        expected = {"data": "value"}
        mock_client.execute.return_value = expected
        result = _execute_graphql_query(mock_client, MagicMock(), {}, logger)
        assert result == expected

    def test_retries_on_retriable_error(
        self, mock_client: MagicMock, logger: logging.Logger
    ) -> None:
        """Should retry up to max_retries times on retriable errors, then succeed."""
        success = {"ok": True}
        mock_client.execute.side_effect = [
            ConnectionError("timeout"),
            ConnectionError("timeout"),
            success,
        ]
        with patch("gov_gh.github_core.sleep"):
            result = _execute_graphql_query(
                mock_client, MagicMock(), {}, logger, max_retries=3
            )
        assert result == success
        assert mock_client.execute.call_count == 3

    def test_raises_after_max_retries_exceeded(
        self, mock_client: MagicMock, logger: logging.Logger
    ) -> None:
        """Should raise after exhausting all retries."""
        mock_client.execute.side_effect = ConnectionError("timeout")
        with patch("gov_gh.github_core.sleep"), pytest.raises(ConnectionError):
            _execute_graphql_query(mock_client, MagicMock(), {}, logger, max_retries=2)

    def test_raises_immediately_on_non_retriable_error(
        self, mock_client: MagicMock, logger: logging.Logger
    ) -> None:
        """Non-retriable errors (TransportQueryError) should propagate immediately."""
        mock_client.execute.side_effect = TransportQueryError("syntax error")
        with pytest.raises(TransportQueryError):
            _execute_graphql_query(mock_client, MagicMock(), {}, logger)
        assert mock_client.execute.call_count == 1

    def test_exponential_backoff_sleep_durations(
        self, mock_client: MagicMock, logger: logging.Logger
    ) -> None:
        """Backoff sleep times should follow 2^(attempt-1): 1s, 2s, 4s…"""
        mock_client.execute.side_effect = [
            ConnectionError(),
            ConnectionError(),
            ConnectionError(),
            {"ok": True},
        ]
        with patch("gov_gh.github_core.sleep") as mock_sleep:
            _execute_graphql_query(mock_client, MagicMock(), {}, logger, max_retries=4)
        assert mock_sleep.call_args_list == [call(1), call(2), call(4)]


# ---------------------------------------------------------------------------
# _get_connection
# ---------------------------------------------------------------------------


class TestGetConnection:
    def test_returns_nested_dict_at_path(self) -> None:
        """Should traverse a nested path and return the dict at the end."""
        result = {"organization": {"repositories": {"nodes": []}}}
        conn = _get_connection(result, ["organization", "repositories"])
        assert conn == {"nodes": []}

    def test_raises_on_missing_key(self) -> None:
        """Should raise GraphQLResponseError when a key in the path is absent."""
        result = {"organization": {}}
        with pytest.raises(GraphQLResponseError):
            _get_connection(result, ["organization", "repositories"])

    def test_raises_on_non_dict_value(self) -> None:
        """Should raise GraphQLResponseError when a path value is not a dict."""
        result = {"organization": "not-a-dict"}
        with pytest.raises(GraphQLResponseError):
            _get_connection(result, ["organization", "repositories"])

    def test_single_key_path(self) -> None:
        """A single-element path should work like a simple dict lookup."""
        result = {"data": {"nodes": [1, 2]}}
        conn = _get_connection(result, ["data"])
        assert conn == {"nodes": [1, 2]}


# ---------------------------------------------------------------------------
# _get_connection_data
# ---------------------------------------------------------------------------


class TestGetConnectionData:
    def test_returns_edges_when_present(self, logger: logging.Logger) -> None:
        """When both edges and nodes exist, edges should take priority."""
        connection = {"edges": [{"node": "a"}], "nodes": ["a"]}
        data = _get_connection_data(connection, logger)
        assert data == [{"node": "a"}]

    def test_returns_nodes_when_edges_absent(self, logger: logging.Logger) -> None:
        """When only nodes are present, nodes should be returned."""
        connection = {"nodes": ["x", "y"]}
        data = _get_connection_data(connection, logger)
        assert data == ["x", "y"]

    def test_raises_when_neither_edges_nor_nodes(self, logger: logging.Logger) -> None:
        """Should raise GraphQLResponseError when the connection has no data key."""
        with pytest.raises(GraphQLResponseError):
            _get_connection_data({}, logger)

    def test_raises_when_edges_is_not_a_list(self, logger: logging.Logger) -> None:
        """Should raise GraphQLResponseError when edges is not a list."""
        with pytest.raises(GraphQLResponseError):
            _get_connection_data({"edges": "bad"}, logger)

    def test_raises_when_nodes_is_not_a_list(self, logger: logging.Logger) -> None:
        """Should raise GraphQLResponseError when nodes is not a list."""
        with pytest.raises(GraphQLResponseError):
            _get_connection_data({"nodes": 42}, logger)


# ---------------------------------------------------------------------------
# paginate_connection
# ---------------------------------------------------------------------------


def _make_page(items: list, has_next: bool, end_cursor: str | None = None) -> dict:
    """Build a minimal GraphQL page response for tests."""
    return {
        "org": {
            "repos": {
                "nodes": items,
                "pageInfo": {"hasNextPage": has_next, "endCursor": end_cursor},
            }
        }
    }


class TestPaginateConnection:
    def test_single_page_yields_all_items(
        self, mock_client: MagicMock, logger: logging.Logger
    ) -> None:
        """A single-page response should yield every node exactly once."""
        mock_client.execute.return_value = _make_page(
            [{"name": "repo1"}, {"name": "repo2"}], has_next=False
        )
        with (
            patch("gov_gh.github_core.gql"),
            patch(
                "gov_gh.github_core._execute_graphql_query",
                return_value=_make_page(
                    [{"name": "repo1"}, {"name": "repo2"}], has_next=False
                ),
            ),
        ):
            items = list(
                paginate_connection(
                    mock_client, "query {}", {}, logger, ["org", "repos"]
                )
            )
        assert items == [{"name": "repo1"}, {"name": "repo2"}]

    def test_multi_page_yields_all_items(
        self, mock_client: MagicMock, logger: logging.Logger
    ) -> None:
        """Multiple pages should be exhausted and all nodes yielded."""
        pages = [
            _make_page([{"name": "a"}], has_next=True, end_cursor="cur1"),
            _make_page([{"name": "b"}], has_next=False),
        ]
        with (
            patch("gov_gh.github_core.gql"),
            patch("gov_gh.github_core._execute_graphql_query", side_effect=pages),
        ):
            items = list(
                paginate_connection(
                    mock_client, "query {}", {}, logger, ["org", "repos"]
                )
            )
        assert items == [{"name": "a"}, {"name": "b"}]

    def test_transform_is_applied(
        self, mock_client: MagicMock, logger: logging.Logger
    ) -> None:
        """The transform callable should be applied to every yielded node."""
        with (
            patch("gov_gh.github_core.gql"),
            patch(
                "gov_gh.github_core._execute_graphql_query",
                return_value=_make_page([{"name": "repo1"}], has_next=False),
            ),
        ):
            items = list(
                paginate_connection(
                    mock_client,
                    "query {}",
                    {},
                    logger,
                    ["org", "repos"],
                    transform=lambda n: n["name"].upper(),
                )
            )
        assert items == ["REPO1"]

    def test_filter_excludes_items(
        self, mock_client: MagicMock, logger: logging.Logger
    ) -> None:
        """The filter predicate should exclude non-matching nodes."""
        with (
            patch("gov_gh.github_core.gql"),
            patch(
                "gov_gh.github_core._execute_graphql_query",
                return_value=_make_page(
                    [{"name": "keep"}, {"name": "drop"}], has_next=False
                ),
            ),
        ):
            items = list(
                paginate_connection(
                    mock_client,
                    "query {}",
                    {},
                    logger,
                    ["org", "repos"],
                    filter=lambda n: n["name"] == "keep",
                )
            )
        assert items == [{"name": "keep"}]

    def test_raises_when_page_info_missing(
        self, mock_client: MagicMock, logger: logging.Logger
    ) -> None:
        """Should raise GraphQLResponseError when pageInfo is absent."""
        response = {"org": {"repos": {"nodes": []}}}  # no pageInfo
        with (
            patch("gov_gh.github_core.gql"),
            patch("gov_gh.github_core._execute_graphql_query", return_value=response),
            pytest.raises(GraphQLResponseError),
        ):
            list(
                paginate_connection(
                    mock_client, "query {}", {}, logger, ["org", "repos"]
                )
            )

    def test_cursor_passed_on_subsequent_pages(
        self, mock_client: MagicMock, logger: logging.Logger
    ) -> None:
        """The endCursor from page N should be passed as cursor in page N+1."""
        pages = [
            _make_page([{"name": "a"}], has_next=True, end_cursor="abc"),
            _make_page([{"name": "b"}], has_next=False),
        ]
        with (
            patch("gov_gh.github_core.gql"),
            patch(
                "gov_gh.github_core._execute_graphql_query", side_effect=pages
            ) as mock_execute,
        ):
            list(
                paginate_connection(
                    mock_client, "query {}", {"org": "myorg"}, logger, ["org", "repos"]
                )
            )
        first_call_vars = mock_execute.call_args_list[0][0][2]
        second_call_vars = mock_execute.call_args_list[1][0][2]
        assert first_call_vars["cursor"] is None
        assert second_call_vars["cursor"] == "abc"
