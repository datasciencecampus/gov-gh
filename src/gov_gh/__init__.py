"""gov-gh: Python SDK for the GitHub REST and GraphQL APIs."""

from importlib.metadata import PackageNotFoundError, version

from gov_gh.client import GitHubClient
from gov_gh.graphql import GraphQLClient
from gov_gh.rest import RESTClient

try:
    __version__ = version("gov-gh")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = ["GitHubClient", "GraphQLClient", "RESTClient", "__version__"]
