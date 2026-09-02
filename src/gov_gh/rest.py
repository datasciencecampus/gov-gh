"""Client for requests to the GitHub REST API."""

from http import HTTPStatus
from logging import Logger, getLogger
from typing import Any

from requests import Response, Session
from requests.exceptions import RequestException

from gov_gh.auth import GitHubAuth
from gov_gh.retry import RetryPolicy

REST_ENDPOINT = "https://api.github.com"
RETRIABLE_STATUS_CODES = frozenset(
    {
        HTTPStatus.INTERNAL_SERVER_ERROR,
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    }
)


class RESTClient:
    """Send authenticated requests to the GitHub REST API."""

    def __init__(
        self,
        auth: GitHubAuth,
        logger: Logger | None = None,
        retry_policy: RetryPolicy | None = None,
        session: Session | None = None,
    ) -> None:
        """Initialise the REST client.

        Args:
            auth: Shared GitHub authentication details.
            logger: Logger used for request retries.
            retry_policy: Retry configuration for transient failures.
            session: Optional requests session, primarily for custom transports.
        """
        self._logger = logger or getLogger(__name__)
        self._retry_policy = retry_policy or RetryPolicy()
        self._session = session or Session()
        self._session.headers.update(auth.headers())

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | list[Any] | None = None,
    ) -> dict[str, Any] | list[Any] | None:
        """Send a request to a relative GitHub REST API path.

        Args:
            method: HTTP method such as ``GET`` or ``POST``.
            path: Relative API path, for example ``/orgs/ons/repos``.
            params: Optional query parameters.
            json: Optional JSON request body.

        Returns:
            The decoded JSON response, or ``None`` for an empty response.

        Raises:
            ValueError: If an absolute URL is supplied.
            requests.HTTPError: If GitHub returns an unsuccessful status.
            requests.RequestException: If the request cannot be completed.
        """
        if "://" in path:
            raise ValueError("path must be relative to the GitHub REST endpoint")

        url = f"{REST_ENDPOINT}/{path.lstrip('/')}"

        def send() -> Response:
            response = self._session.request(
                method.upper(), url, params=params, json=json, timeout=30
            )
            response.raise_for_status()
            return response

        response = self._retry_policy.execute(
            send, self._is_retriable, self._logger, f"REST {method.upper()} {path}"
        )
        if response.status_code == HTTPStatus.NO_CONTENT or not response.content:
            return None
        result: dict[str, Any] | list[Any] = response.json()
        return result

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()

    @staticmethod
    def _is_retriable(error: Exception) -> bool:
        if not isinstance(error, RequestException):
            return False
        response = error.response
        return response is None or response.status_code in RETRIABLE_STATUS_CODES
