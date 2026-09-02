"""Top-level client for the GitHub REST and GraphQL APIs."""

from logging import Logger

from pydantic import SecretStr

from gov_gh.auth import GitHubAuth
from gov_gh.graphql import GraphQLClient
from gov_gh.rest import RESTClient
from gov_gh.retry import RetryPolicy


class GitHubClient:
    """Provide REST and GraphQL clients using shared authentication settings."""

    def __init__(
        self,
        token: str | SecretStr,
        *,
        logger: Logger | None = None,
        max_retries: int = 3,
    ) -> None:
        """Initialise GitHub API clients.

        Args:
            token: GitHub personal access token or installation token.
            logger: Optional logger shared by both protocol clients.
            max_retries: Number of retries after an initial failed request.

        Raises:
            ValueError: If the token is empty or max_retries is negative.

        Example:
            >>> client = GitHubClient("github-token")
            >>> repositories = client.rest.request("GET", "/user/repos")
        """
        auth = GitHubAuth.from_token(token)
        retry_policy = RetryPolicy(max_retries=max_retries)
        self.rest = RESTClient(auth, logger, retry_policy)
        self.graphql = GraphQLClient(auth, logger, retry_policy)

    def close(self) -> None:
        """Release resources held by the protocol clients."""
        self.rest.close()

    def __enter__(self) -> "GitHubClient":
        """Return this client from a context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Release resources when leaving a context manager."""
        self.close()
