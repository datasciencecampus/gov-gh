"""Retry policy shared by GitHub API transports."""

from collections.abc import Callable
from dataclasses import dataclass
from logging import Logger
from time import sleep


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Execute operations with exponential backoff for transient failures."""

    max_retries: int = 3

    def __post_init__(self) -> None:
        """Validate retry configuration."""
        if self.max_retries < 0:
            raise ValueError("max_retries must be greater than or equal to zero")

    def execute[T](
        self,
        operation: Callable[[], T],
        should_retry: Callable[[Exception], bool],
        logger: Logger,
        operation_name: str,
    ) -> T:
        """Execute an operation and retry failures accepted by the predicate.

        Args:
            operation: Callable containing the request to execute.
            should_retry: Predicate identifying transient exceptions.
            logger: Logger used to report retry attempts.
            operation_name: Human-readable operation name for log messages.

        Returns:
            The successful operation result.

        Raises:
            Exception: The final or non-retriable exception from the operation.
        """
        attempt = 0
        while True:
            try:
                return operation()
            except Exception as error:
                if not should_retry(error) or attempt >= self.max_retries:
                    raise
                attempt += 1
                backoff = 2 ** (attempt - 1)
                logger.warning(
                    "%s failed on attempt %d/%d: %s. Retrying in %d seconds",
                    operation_name,
                    attempt,
                    self.max_retries,
                    error,
                    backoff,
                )
                sleep(backoff)
