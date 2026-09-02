"""Authentication helpers shared by GitHub API clients."""

from dataclasses import dataclass

from pydantic import SecretStr

DEFAULT_ACCEPT_HEADER = "application/vnd.github+json"
DEFAULT_API_VERSION = "2022-11-28"


@dataclass(frozen=True, slots=True)
class GitHubAuth:
    """Build authentication headers without exposing the stored token."""

    token: SecretStr

    @classmethod
    def from_token(cls, token: str | SecretStr) -> "GitHubAuth":
        """Create authentication details from a plain or protected token.

        Args:
            token: GitHub personal access token or installation token.

        Returns:
            Authentication details containing a protected token.

        Raises:
            ValueError: If the token is empty.
        """
        secret = token if isinstance(token, SecretStr) else SecretStr(token)
        if not secret.get_secret_value().strip():
            raise ValueError("GitHub token must not be empty")
        return cls(secret)

    def headers(self) -> dict[str, str]:
        """Return headers accepted by both GitHub REST and GraphQL APIs.

        Returns:
            Authentication, media type, and API version headers.
        """
        return {
            "Authorization": f"Bearer {self.token.get_secret_value()}",
            "Accept": DEFAULT_ACCEPT_HEADER,
            "X-GitHub-Api-Version": DEFAULT_API_VERSION,
        }
