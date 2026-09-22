from collections.abc import Callable, Iterator
from http import HTTPStatus
from logging import Logger, getLogger
from time import sleep
from typing import Any

import requests
from gql import Client, gql
from gql.transport.exceptions import TransportQueryError, TransportServerError
from gql.transport.requests import RequestsHTTPTransport
from pydantic import SecretStr

from gov_gh.exceptions import GraphQLResponseError

GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
REST_API_BASE_URL = "https://api.github.com"
REST_PAGE_SIZE = 100


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
        dict[str, Any]: The result of the GraphQL query execution.

    Raises:
        Exception: If the query fails after retries or with a non-retriable error.
    """

    def run_query() -> dict[str, Any]:
        result: dict[str, Any] = client.execute(query, variable_values=variables)
        return result

    return _execute_with_retries(
        operation=run_query,
        logger=logger,
        max_retries=max_retries,
        is_retriable=_is_retriable,
        operation_name="GraphQL query",
    )


def _execute_with_retries[T](
    operation: Callable[[], T],
    logger: Logger,
    max_retries: int,
    is_retriable: Callable[[Exception], bool],
    operation_name: str,
) -> T:
    """Execute an operation with retry/backoff for retriable failures.

    Args:
        operation: Zero-argument callable that performs the operation.
        logger: Logger instance for retry and failure logging.
        max_retries: Maximum number of retry attempts.
        is_retriable: Predicate deciding whether an exception should be retried.
        operation_name: Human-readable operation name for logs.

    Returns:
        T: The operation result.

    Raises:
        ValueError: If ``max_retries`` is less than 1.
        Exception: Re-raises the underlying operation error once retries are exhausted
            or if the error is non-retriable.
    """
    if max_retries < 1:
        raise ValueError("max_retries must be at least 1")

    retry_count = 0
    while True:
        try:
            return operation()
        except Exception as error:
            if is_retriable(error):
                if retry_count < max_retries:
                    retry_count += 1
                    backoff = 2 ** (retry_count - 1)
                    logger.warning(
                        "%s attempt %d/%d failed with retriable error %s. "
                        "Retrying in %d seconds...",
                        operation_name,
                        retry_count,
                        max_retries,
                        error,
                        backoff,
                    )
                    sleep(backoff)
                else:
                    logger.error(
                        "%s failed after %d/%d attempts",
                        operation_name,
                        retry_count,
                        max_retries,
                    )
                    raise
            else:
                logger.error(
                    "%s failed with non-retriable error: %s", operation_name, error
                )
                raise


def _execute_rest_get(
    url: str,
    token: SecretStr,
    logger: Logger,
    page: int,
    page_size: int,
    max_retries: int = 3,
) -> requests.Response:
    """Execute a GitHub REST GET request with retry logic.

    Args:
        url: Full REST endpoint URL.
        token: Personal access token.
        logger: Logger instance for retry and failure logging.
        page: Page number to fetch.
        page_size: Number of items per page.
        max_retries: Maximum number of retry attempts.

    Returns:
        requests.Response: Successful HTTP response.

    Raises:
        requests.RequestException: If retries are exhausted.
    """

    def run_request() -> requests.Response:
        response = requests.get(
            url,
            headers=_get_auth_headers(token),
            params={"per_page": page_size, "page": page},
            timeout=30,
        )
        response.raise_for_status()
        return response

    return _execute_with_retries(
        operation=run_request,
        logger=logger,
        max_retries=max_retries,
        is_retriable=_is_retriable,
        operation_name=f"REST request to {url}",
    )


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


def _paginate_items[T, S](
    initial_state: S,
    fetch_page: Callable[[S], tuple[list[dict[str, Any]], S | None]],
    transform: Callable[[dict[str, Any]], T] = (lambda x: x),
    filter: Callable[[dict[str, Any]], bool] = (lambda _item: True),
) -> Iterator[T]:
    """Yield transformed items from a generic paginated source.

    Args:
        initial_state: Initial pagination state (for example page number or cursor).
        fetch_page: Callable returning ``(items, next_state)`` for the current state.
        transform: Optional function to transform each item before yielding.
        filter: Optional predicate to include items before transformation.

    Yields:
        T: Transformed items from all pages.
    """
    state = initial_state
    while True:
        items, next_state = fetch_page(state)
        for item in items:
            if filter(item):
                yield transform(item)
        if next_state is None:
            return
        state = next_state


def paginate_graphql_connection[T](
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
    """Paginate a GraphQL connection.

    Args:
        client: Configured GraphQL client instance.
        query_str: GraphQL query string with $cursor variable.
        variables: Variables for the GraphQL query.
        logger: Logger instance for logging pagination progress.
        connection_path: Path to the GraphQL connection field in the response.
        node_key: Key for nodes within the connection (default ``"nodes"``).
        page_size: Number of items per page (default is 50).
        transform: Optional function to transform raw node/edge dicts.
        filter: Optional predicate to select raw node/edge dicts.

    Yields:
        T: Transformed items from the GraphQL connection.
    """
    query = gql(query_str)
    page_index = 0
    total_items = 0

    def fetch_page(cursor: str | None) -> tuple[list[dict[str, Any]], str | None]:
        nonlocal page_index
        nonlocal total_items
        n_variables = variables | {"cursor": cursor}
        result = _execute_graphql_query(client, query, n_variables, logger)
        connection = _get_connection(result, connection_path)
        data = _get_connection_data(connection, logger)
        total_items += len(data)
        page_info = connection.get("pageInfo")
        if not page_info:
            raise GraphQLResponseError(
                f"Unexpected Response: {connection_path} pageInfo is missing"
            )
        if page_info.get("hasNextPage"):
            next_cursor = page_info.get("endCursor")
            page_index += 1
            return data, next_cursor
        return data, None

    yield from _paginate_items(
        initial_state=None,
        fetch_page=fetch_page,
        transform=transform,
        filter=filter,
    )
    logger.info(
        "Pagination complete after %d pages, %d total items for "
        "connection path: %s (page_size: %d)",
        page_index + 1,
        total_items,
        connection_path,
        page_size,
    )


def paginate_rest_collection[T](
    url: str,
    token: SecretStr,
    logger: Logger,
    page_size: int = 50,
    max_retries: int = 3,
    transform: Callable[[dict[str, Any]], T] = (lambda x: x),
    filter: Callable[[dict[str, Any]], bool] = (lambda _item: True),
) -> Iterator[T]:
    """Paginate a REST collection endpoint.

    Args:
        url: Full REST endpoint URL.
        token: Personal access token with required permissions.
        logger: Logger instance for retry and progress logging.
        page_size: Number of items per page (default is 50).
        max_retries: Maximum retries for transient request failures.
        transform: Optional function to transform raw item dicts.
        filter: Optional predicate to select raw item dicts.

    Yields:
        T: Transformed items from the REST collection.

    Raises:
        ValueError: If ``max_retries`` is less than 1.
        requests.RequestException: If request retries are exhausted.
        TypeError: If the endpoint does not return a JSON list payload.
    """

    if page_size < 1:
        raise ValueError("page_size must be at least 1")

    def fetch_page(page: int) -> tuple[list[dict[str, Any]], int | None]:
        response = _execute_rest_get(
            url=url,
            token=token,
            logger=logger,
            page=page,
            page_size=page_size,
            max_retries=max_retries,
        )
        payload: Any = response.json()
        if not isinstance(payload, list):
            raise TypeError(f"Expected a list response from {url}")

        items = [item for item in payload if isinstance(item, dict)]
        if len(payload) < page_size:
            return items, None
        return items, page + 1

    yield from _paginate_items(
        initial_state=1,
        fetch_page=fetch_page,
        transform=transform,
        filter=filter,
    )


def fetch_org_teams(
    org: str, token: SecretStr, page_size: int = 50
) -> Iterator[dict[str, Any]]:
    """Iterate over all teams in a GitHub organisation.

    Args:
        org: GitHub organisation login.
        token: Personal access token with organisation read permissions.
        page_size: Number of teams to request per page.

    Yields:
        Raw team nodes from the GraphQL response.
    """
    query_str = f"""
    query($org: String!, $cursor: String) {{
      organization(login: $org) {{
        teams(first: {page_size}, after: $cursor) {{
          nodes {{
            name
            slug
          }}
          pageInfo {{ hasNextPage endCursor }}
        }}
      }}
    }}
    """.strip()

    client = _get_graphql_client(token)
    yield from paginate_graphql_connection(
        client=client,
        query_str=query_str,
        variables={"org": org},
        logger=getLogger(__name__),
        connection_path=["organization", "teams"],
        page_size=page_size,
    )


def fetch_org_members(
    org: str, token: SecretStr, page_size: int = 50
) -> Iterator[dict[str, Any]]:
    """Iterate over all organisation members.

    Args:
        org: GitHub organisation login.
        token: Personal access token with organisation read permissions.
        page_size: Number of members to request per page.

    Yields:
        Raw member nodes from the GraphQL response.
    """
    query_str = f"""
    query($org: String!, $cursor: String) {{
      organization(login: $org) {{
        membersWithRole(first: {page_size}, after: $cursor) {{
          nodes {{
            login
            name
          }}
          pageInfo {{ hasNextPage endCursor }}
        }}
      }}
    }}
    """.strip()

    client = _get_graphql_client(token)
    yield from paginate_graphql_connection(
        client=client,
        query_str=query_str,
        variables={"org": org},
        logger=getLogger(__name__),
        connection_path=["organization", "membersWithRole"],
        page_size=page_size,
    )


def fetch_org_owners(
    org: str, token: SecretStr, page_size: int = 50
) -> Iterator[dict[str, Any]]:
    """Iterate over organisation owners (admin role members).

    Args:
        org: GitHub organisation login.
        token: Personal access token with organisation read permissions.
        page_size: Number of members to request per page.

    Yields:
        Owner member records containing ``login`` and optional ``name``.
    """

    def _is_owner_edge(edge: dict[str, Any]) -> bool:
        if edge.get("role") != "ADMIN":
            return False
        node = edge.get("node")
        if not isinstance(node, dict):
            return False
        return isinstance(node.get("login"), str) and bool(node.get("login"))

    def _owner_from_edge(edge: dict[str, Any]) -> dict[str, Any]:
        node = edge.get("node")
        if not isinstance(node, dict):
            return {}
        owner: dict[str, Any] = {"login": node.get("login")}
        if isinstance(node.get("name"), str):
            owner["name"] = node.get("name")
        return owner

    query_str = f"""
    query($org: String!, $cursor: String) {{
      organization(login: $org) {{
        membersWithRole(first: {page_size}, after: $cursor) {{
          edges {{
            role
            node {{
              login
              name
            }}
          }}
          pageInfo {{ hasNextPage endCursor }}
        }}
      }}
    }}
    """.strip()

    client = _get_graphql_client(token)
    yield from paginate_graphql_connection(
        client=client,
        query_str=query_str,
        variables={"org": org},
        logger=getLogger(__name__),
        connection_path=["organization", "membersWithRole"],
        node_key="edges",
        page_size=page_size,
        transform=_owner_from_edge,
        filter=_is_owner_edge,
    )


def fetch_org_invitations(org: str, token: SecretStr) -> list[dict[str, Any]]:
    """Fetch pending organisation invitations via REST.

    Args:
        org: GitHub organisation login.
        token: Personal access token with invitations read permissions.

    Returns:
        Raw invitation objects returned by ``GET /orgs/{org}/invitations``.
    """
    url = f"{REST_API_BASE_URL}/orgs/{org}/invitations"
    return list(
        paginate_rest_collection(
            url=url,
            token=token,
            logger=getLogger(__name__),
            page_size=REST_PAGE_SIZE,
        )
    )
