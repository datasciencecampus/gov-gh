"""gov-gh: Python SDK for the GitHub REST and GraphQL APIs."""

from importlib.metadata import PackageNotFoundError, version

from gov_gh.github_core import (
    fetch_org_members,
    fetch_org_owners,
    fetch_org_teams,
)

try:
    __version__ = version("gov-gh")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = [
    "__version__",
    "fetch_org_members",
    "fetch_org_owners",
    "fetch_org_teams",
]
