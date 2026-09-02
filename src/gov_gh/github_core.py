from collections.abc import Callable, Iterator
from http import HTTPStatus
from logging import Logger
from time import sleep
from typing import Any

from gql import Client, gql
from gql.transport.exceptions import TransportQueryError, TransportServerError
from gql.transport.requests import RequestsHTTPTransport
from pydantic import SecretStr

from gov_gh.exceptions import GraphQLResponseError

GRAPHQL_ENDPOINT = "https://api.github.com/graphql"

RETRIABLE_HTTP_STATUS_CODES: frozenset[HTTPStatus] = frozenset(
    {
        HTTPStatus.INTERNAL_SERVER_ERROR,  # 500
        HTTPStatus.BAD_GATEWAY,  # 502
        HTTPStatus.SERVICE_UNAVAILABLE,  # 503
        HTTPStatus.GATEWAY_TIMEOUT,  # 504
    }
)


def _get_auth_headers(token: SecretStr) -> dict:
    """Generate authentication headers for GitHub API requests.
    Works for both REST and GraphQL endpoints.
    """
    return {
        "Authorization": f"Bearer {token.get_secret_value()}",
        "Accept": "application/vnd.github+json",
    }


def _get_graphql_client(token: SecretStr) -> Client:
    """Create a configured GraphQL client instance.
    Args:
        token: Personal access token with appropriate permissions.
    Returns:
        Client: Configured GraphQL client instance.
    """
    transport = RequestsHTTPTransport(
        url=GRAPHQL_ENDPOINT,
        headers=_get_auth_headers(token),
        timeout=30,
        verify=True,
    )
    return Client(transport=transport, fetch_schema_from_transport=True)


def _is_retriable(error: Exception) -> bool:
    """Determine if an error is retriable based on its type and HTTP status code."""
    if isinstance(error, TransportQueryError):  # Forbidden, Syntax Errors
        return False
    if isinstance(
        error, TransportServerError
    ):  # HTTP Level Errors 404, 403 should not be retried, but some 5xx may
        return error.code in RETRIABLE_HTTP_STATUS_CODES
    return True


def _execute_graphql_query(
    client: Client,
    query: str,
    variables: dict[str, Any],
    logger: Logger,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Execute a GraphQL query with retry logic for transient errors.
    Args:
        client: Configured GraphQL client instance.
        query: Compiled GraphQL query object.
        variables: Dictionary of variables to pass to the query.
        logger: Logger instance for logging retries and errors.
        max_retries: Maximum number of retry attempts for transient errors.
    Returns:
        Dict[str, Any]: The result of the GraphQL query execution.
    Raises:
        Exception: If the query fails after the maximum number of retries or a
            non-retriable error occurs.
    """
    attempt = 0
    while True:
        try:
            result: dict[str, Any] = client.execute(query, variable_values=variables)
            return result
        except Exception as e:
            if _is_retriable(e):
                if attempt < max_retries:  # Case retriable
                    attempt += 1
                    backoff = 2 ** (attempt - 1)
                    logger.warning(
                        "GraphQL query attempt %d/%d failed with retriable "
                        "error %s. Retrying in %d seconds...",
                        attempt,
                        max_retries,
                        e,
                        backoff,
                    )
                    sleep(backoff)
                else:  # Too many retries
                    logger.error(
                        "GraphQL query failed after %d/%d attempts",
                        attempt,
                        max_retries,
                    )
                    raise
            else:  # Non-retriable error
                logger.error("GraphQL query failed with non-retriable error: %s", e)
                raise


def _get_connection(
    result: dict[str, Any], connection_path: list[str]
) -> dict[str, Any]:
    """Extract the connection data from a GraphQL result based on the provided path.

    Args:
        result: The GraphQL query result.
        connection_path: The path to the connection field in the result.
    Returns:
        dict[str, Any]: The connection data extracted from the result.
    Raises:
        GraphQLResponseError: If the connection path is not found in the result.
    """
    connection = result
    for key in connection_path:
        connection = connection.get(key)
        if connection is None:
            raise GraphQLResponseError(f"Unexpected Response: {key} is missing")
        elif not isinstance(connection, dict):
            raise GraphQLResponseError(f"Unexpected Response: {key} is not a dict")
    return connection


def _get_connection_data(
    connection: dict[str, Any], logger: Logger
) -> list[dict[str, Any]]:
    """Extract the nodes or edges from a GraphQL result.

    args:
        connection: The GraphQL query result.
        logger: Logger instance for logging.
    Returns:
        dict[str, Any] | None: The node or edges if edges available defaults to edges
    """
    edges = connection.get("edges")
    nodes = connection.get("nodes")
    if edges is not None:
        if not isinstance(edges, list):
            raise GraphQLResponseError("Unexpected Response: edges is not a list")
        else:
            logger.debug("Edges found in connection: %d", len(edges))
            return edges
    elif nodes is not None:
        if not isinstance(nodes, list):
            raise GraphQLResponseError("Unexpected Response: nodes is not a list")
        else:
            logger.debug("Nodes found in connection: %d", len(nodes))
            return nodes
    else:
        raise GraphQLResponseError(
            "Unexpected Response: neither edges nor nodes are present"
        )


def paginate_connection[T](
    client: Client,
    query_str: str,
    variables: dict[str, Any],
    logger: Logger,
    connection_path: list[str],
    node_key: str = "nodes",
    page_size: int = 50,
    transform: Callable[[dict[str, Any]], T] = (lambda x: x),
    filter: Callable[[dict[str, Any]], bool] = (lambda _node: True),
) -> Iterator[T]:
    """Helper to paginate through a GraphQL connection.
    Args:
        client: Configured GraphQL client instance.
        query_str: GraphQL query string with $org and $cursor variables.
        variables: Variables for the GraphQL query.
        logger: Logger instance for logging pagination progress.
        connection_path: Path to the connection field in the GraphQL response
            (e.g. ["organization", "repositories"]).
        node_key: Key for the nodes in the connection (default is "nodes").
        page_size: Number of items per page (default is 50).
        transform: Optional function to transform raw node or edge dicts before
            yielding (default is identity).
        filter: Optional predicate to filter raw node or edge dicts before
            transformation/yielding (default yields all).
    Yields:
        T: Transformed node from the connection.
    """
    query = gql(query_str)
    cursor: str | None = None
    page_index = 0
    while True:
        n_variables = variables | {"cursor": cursor}
        result = _execute_graphql_query(client, query, n_variables, logger)
        connection = _get_connection(result, connection_path)
        data = _get_connection_data(connection, logger)
        for item in data:
            if filter(item):
                yield transform(item)
        page_info = connection.get("pageInfo")
        if not page_info:
            raise GraphQLResponseError(
                f"Unexpected Response: {connection_path} pageInfo is missing"
            )
        if page_info.get("hasNextPage"):
            cursor = page_info.get("endCursor")
            page_index += 1
        else:
            logger.info(
                "Pagination complete after %d pages, %d total items for "
                "connection path: %s (page_size: %d)",
                page_index + 1,
                page_index * page_size + len(data),
                connection_path,
                page_size,
            )
            break
