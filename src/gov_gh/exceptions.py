"""Exceptions raised while interacting with GitHub APIs."""


class GraphQLResponseError(Exception):
    """Raised when a GraphQL response has an unexpected structure."""
