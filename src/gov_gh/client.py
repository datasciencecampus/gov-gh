"""Top-level client for the GitHub GraphQL API."""

from logging import Logger

from pydantic import SecretStr

from gov_gh.auth import GitHubAuth
from gov_gh.graphql import GraphQLClient
from gov_gh.retry import RetryPolicy


class GitHubClient:
    """Provide a GraphQL client with shared authentication and retry settings."""

    def __init__(
        self,
        token: str | SecretStr,
        *,
        logger: Logger | None = None,
        max_retries: int = 3,
    ) -> None:
        """Initialise the GitHub GraphQL API client.

        Args:
            token: GitHub personal access token or installation token.
            logger: Optional logger used for GraphQL requests.
            max_retries: Number of retries after an initial failed request.

        Raises:
            ValueError: If the token is empty or max_retries is negative.

        Example:
            >>> client = GitHubClient("github-token")
            >>> graphql = client.graphql
        """
        auth = GitHubAuth.from_token(token)
        retry_policy = RetryPolicy(max_retries=max_retries)
        self.graphql = GraphQLClient(auth, logger, retry_policy)
