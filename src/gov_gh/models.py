"""Shared Pydantic models for GitHub API payloads."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GraphQLVariables(BaseModel):
    """Base model for validated variables sent with a GraphQL operation."""

    model_config = ConfigDict(extra="forbid")


class GraphQLPageInfo(BaseModel):
    """Pagination metadata returned for a GraphQL connection."""

    model_config = ConfigDict(populate_by_name=True)

    has_next_page: bool = Field(alias="hasNextPage")
    end_cursor: str | None = Field(default=None, alias="endCursor")

    @model_validator(mode="after")
    def validate_end_cursor(self) -> "GraphQLPageInfo":
        """Require a cursor when another page is available.

        Returns:
            The validated pagination metadata.

        Raises:
            ValueError: If another page exists without an end cursor.
        """
        if self.has_next_page and self.end_cursor is None:
            raise ValueError("endCursor is required when hasNextPage is true")
        return self


class GraphQLConnection[ItemT: BaseModel](BaseModel):
    """A validated node or edge connection returned by GraphQL."""

    model_config = ConfigDict(populate_by_name=True)

    page_info: GraphQLPageInfo = Field(alias="pageInfo")
    nodes: list[ItemT] | None = None
    edges: list[ItemT] | None = None

    @model_validator(mode="after")
    def validate_items(self) -> "GraphQLConnection[ItemT]":
        """Require exactly one supported collection shape.

        Returns:
            The validated connection.

        Raises:
            ValueError: If neither or both item collections are present.
        """
        if (self.nodes is None) == (self.edges is None):
            raise ValueError("connection must contain either nodes or edges")
        return self

    @property
    def items(self) -> list[ItemT]:
        """Return the populated node or edge collection.

        Returns:
            The validated connection items.
        """
        return self.nodes if self.nodes is not None else self.edges or []
