"""gov-gh: Python SDK for the GitHub GraphQL API."""

from importlib.metadata import PackageNotFoundError, version

from gov_gh.client import GitHubClient
from gov_gh.graphql import GraphQLClient
from gov_gh.models import GraphQLConnection, GraphQLPageInfo, GraphQLVariables

try:
    __version__ = version("gov-gh")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = [
    "GitHubClient",
    "GraphQLClient",
    "GraphQLConnection",
    "GraphQLPageInfo",
    "GraphQLVariables",
    "__version__",
]
