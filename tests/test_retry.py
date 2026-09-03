"""Tests for the shared retry policy."""

import logging
from unittest.mock import call, patch

import pytest

from gov_gh.retry import RetryPolicy


def test_retry_policy_uses_exponential_backoff() -> None:
    """Transient failures should back off exponentially before succeeding."""
    outcomes: list[Exception | str] = [ConnectionError(), ConnectionError(), "ok"]

    def operation() -> str:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    with patch("gov_gh.retry.sleep") as mock_sleep:
        result = RetryPolicy(max_retries=2).execute(
            operation,
            lambda error: isinstance(error, ConnectionError),
            logging.getLogger(__name__),
            "test operation",
        )

    assert result == "ok"
    assert mock_sleep.call_args_list == [call(1), call(2)]


def test_retry_policy_does_not_retry_rejected_error() -> None:
    """An error rejected by the retry predicate should be raised immediately."""
    with pytest.raises(ValueError, match="invalid"):
        RetryPolicy().execute(
            lambda: (_ for _ in ()).throw(ValueError("invalid")),
            lambda _error: False,
            logging.getLogger(__name__),
            "test operation",
        )
