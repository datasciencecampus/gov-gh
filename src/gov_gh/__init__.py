"""gov-gh: Python SDK for the GitHub REST and GraphQL APIs."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("gov-gh")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = ["__version__"]
