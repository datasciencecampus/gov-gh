"""Client and pagination helpers for the GitHub GraphQL API."""

from collections.abc import Callable, Iterator
from http import HTTPStatus
from logging import Logger, getLogger
from typing import Any

from gql import Client, gql
from gql.transport.exceptions import TransportQueryError, TransportServerError
from gql.transport.requests import RequestsHTTPTransport

from gov_gh.auth import GitHubAuth
from gov_gh.exceptions import GraphQLResponseError
from gov_gh.retry import RetryPolicy

GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
RETRIABLE_STATUS_CODES = frozenset(
    {
        HTTPStatus.INTERNAL_SERVER_ERROR,
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    }
)


class GraphQLClient:
    """Execute authenticated queries against the GitHub GraphQL API."""

    def __init__(
        self,
        auth: GitHubAuth,
        logger: Logger | None = None,
        retry_policy: RetryPolicy | None = None,
        client: Client | None = None,
    ) -> None:
        """Initialise the GraphQL client.

        Args:
            auth: Shared GitHub authentication details.
            logger: Logger used for request retries and pagination.
            retry_policy: Retry configuration for transient failures.
            client: Optional gql client, primarily for custom transports.
        """
        self._logger = logger or getLogger(__name__)
        self._retry_policy = retry_policy or RetryPolicy()
        self._client = client or self._create_client(auth)

    def execute(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a GraphQL query with retry handling.

        Args:
            query: GraphQL query or mutation document.
            variables: Optional variables referenced by the document.

        Returns:
            The decoded GraphQL response data.

        Raises:
            gql.transport.exceptions.TransportError: If execution fails.
        """
        document = gql(query)

        def send() -> dict[str, Any]:
            result: dict[str, Any] = self._client.execute(
                document, variable_values=variables or {}
            )
            return result

        return self._retry_policy.execute(
            send, self._is_retriable, self._logger, "GraphQL query"
        )

    def paginate[T](
        self,
        query: str,
        variables: dict[str, Any],
        connection_path: list[str],
        *,
        transform: Callable[[dict[str, Any]], T] = lambda item: item,
        predicate: Callable[[dict[str, Any]], bool] = lambda _item: True,
    ) -> Iterator[T]:
        """Yield all items from a cursor-based GraphQL connection.

        Args:
            query: Query containing a ``$cursor`` variable.
            variables: Query variables other than the cursor.
            connection_path: Keys leading to the connection in each response.
            transform: Function applied to each item before it is yielded.
            predicate: Function selecting which items to yield.

        Yields:
            Items from every page after filtering and transformation.

        Raises:
            GraphQLResponseError: If a response has an invalid connection shape.
        """
        cursor: str | None = None
        while True:
            result = self.execute(query, variables | {"cursor": cursor})
            connection = _get_connection(result, connection_path)
            for item in _get_connection_data(connection):
                if predicate(item):
                    yield transform(item)

            page_info = connection.get("pageInfo")
            if not isinstance(page_info, dict):
                raise GraphQLResponseError(
                    f"Unexpected response: {connection_path} pageInfo is missing"
                )
            if not page_info.get("hasNextPage"):
                return
            cursor = page_info.get("endCursor")
            if not isinstance(cursor, str) or not cursor:
                raise GraphQLResponseError(
                    "Unexpected response: endCursor is missing for the next page"
                )

    @staticmethod
    def _create_client(auth: GitHubAuth) -> Client:
        transport = RequestsHTTPTransport(
            url=GRAPHQL_ENDPOINT,
            headers=auth.headers(),
            timeout=30,
            verify=True,
        )
        return Client(transport=transport, fetch_schema_from_transport=True)

    @staticmethod
    def _is_retriable(error: Exception) -> bool:
        if isinstance(error, TransportQueryError):
            return False
        if isinstance(error, TransportServerError):
            return error.code in RETRIABLE_STATUS_CODES
        return True


def _get_connection(
    result: dict[str, Any], connection_path: list[str]
) -> dict[str, Any]:
    connection = result
    for key in connection_path:
        value = connection.get(key)
        if not isinstance(value, dict):
            raise GraphQLResponseError(
                f"Unexpected response: {key} is missing or is not an object"
            )
        connection = value
    return connection


def _get_connection_data(connection: dict[str, Any]) -> list[dict[str, Any]]:
    data = connection.get("edges")
    if data is None:
        data = connection.get("nodes")
    if not isinstance(data, list):
        raise GraphQLResponseError(
            "Unexpected response: edges or nodes must contain a list"
        )
    if not all(isinstance(item, dict) for item in data):
        raise GraphQLResponseError(
            "Unexpected response: connection items must be objects"
        )
    return data
