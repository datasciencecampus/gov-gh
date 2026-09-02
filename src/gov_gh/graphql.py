"""Client and pagination helpers for the GitHub GraphQL API."""

from collections.abc import Callable, Iterator
from http import HTTPStatus
from logging import Logger, getLogger

from gql import Client, gql
from gql.transport.exceptions import TransportQueryError, TransportServerError
from gql.transport.requests import RequestsHTTPTransport
from pydantic import BaseModel, ValidationError

from gov_gh.auth import GitHubAuth
from gov_gh.models import GraphQLConnection, GraphQLVariables
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

    def execute[ResultT: BaseModel](
        self,
        query: str,
        variables: GraphQLVariables | None,
        *,
        result_model: type[ResultT],
    ) -> ResultT:
        """Execute a GraphQL query with retry handling.

        Args:
            query: GraphQL query or mutation document.
            variables: Validated variables referenced by the document.
            result_model: Pydantic model used to validate the response data.

        Returns:
            The validated GraphQL response model.

        Raises:
            gql.transport.exceptions.TransportError: If execution fails.
            pydantic.ValidationError: If the response does not match the model.
        """
        document = gql(query)
        variable_values = (
            variables.model_dump(mode="json", by_alias=True)
            if variables is not None
            else {}
        )

        def send() -> ResultT:
            result = self._client.execute(document, variable_values=variable_values)
            return result_model.model_validate(result)

        return self._retry_policy.execute(
            send, self._is_retriable, self._logger, "GraphQL query"
        )

    def paginate[PageT: BaseModel, ItemT: BaseModel](
        self,
        query: str,
        variables: GraphQLVariables,
        *,
        result_model: type[PageT],
        get_connection: Callable[[PageT], GraphQLConnection[ItemT]],
        predicate: Callable[[ItemT], bool] = lambda _item: True,
    ) -> Iterator[ItemT]:
        """Yield all items from a cursor-based GraphQL connection.

        Args:
            query: Query containing a ``$cursor`` variable.
            variables: Validated query variables, including a cursor field.
            result_model: Pydantic model used to validate each response page.
            get_connection: Function selecting the connection from a response page.
            predicate: Function selecting which items to yield.

        Yields:
            Validated items from every page after filtering.

        Raises:
            pydantic.ValidationError: If variables or a response page are invalid.
        """
        cursor: str | None = None
        while True:
            page_variables = type(variables).model_validate(
                variables.model_dump() | {"cursor": cursor}
            )
            result = self.execute(query, page_variables, result_model=result_model)
            connection = get_connection(result)
            for item in connection.items:
                if predicate(item):
                    yield item

            if not connection.page_info.has_next_page:
                return
            cursor = connection.page_info.end_cursor

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
        if isinstance(error, (TransportQueryError, ValidationError)):
            return False
        if isinstance(error, TransportServerError):
            return error.code in RETRIABLE_STATUS_CODES
        return True
