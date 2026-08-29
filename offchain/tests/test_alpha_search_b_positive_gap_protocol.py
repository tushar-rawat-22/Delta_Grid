from __future__ import annotations

import numpy as np

from offchain.research.alpha_search_b.engine import (
    MIN_POSITIVE_GAPS,
    nearest_rank,
    rolling_comparison,
    slow_rolling_comparison,
)


def test_positive_gap_threshold_keeps_frozen_protocol_minimum() -> None:
    """A caller-supplied minimum must not weaken the positive-gap protocol floor."""

    assert MIN_POSITIVE_GAPS == 1_000

    history = np.arange(1, MIN_POSITIVE_GAPS + 1, dtype=float)
    values = np.concatenate([history, np.array([2_000.0])])

    result, eligible = rolling_comparison(
        values,
        0.95,
        window=MIN_POSITIVE_GAPS,
        minimum=1,
        positive_only=True,
    )

    expected_threshold = nearest_rank(history, 0.95)
    assert expected_threshold == 950.0
    assert eligible[-1]
    assert result[-1] == (values[-1] > expected_threshold)

    insufficient = values.copy()
    insufficient[0] = 0.0
    result, eligible = rolling_comparison(
        insufficient,
        0.95,
        window=MIN_POSITIVE_GAPS,
        minimum=1,
        positive_only=True,
    )

    assert not eligible[-1]
    assert not result[-1]


def test_positive_gap_reference_matches_frozen_protocol_floor() -> None:
    """The slow oracle must enforce the same positive-history floor as production."""

    history = np.arange(1, MIN_POSITIVE_GAPS + 1, dtype=float)
    values = np.concatenate([history, np.array([2_000.0])])

    fast = rolling_comparison(
        values,
        0.95,
        window=MIN_POSITIVE_GAPS,
        minimum=1,
        positive_only=True,
    )
    slow = slow_rolling_comparison(
        values,
        0.95,
        window=MIN_POSITIVE_GAPS,
        minimum=1,
        positive_only=True,
    )
    assert np.array_equal(fast[0], slow[0])
    assert np.array_equal(fast[1], slow[1])

    insufficient = values.copy()
    insufficient[0] = 0.0
    fast = rolling_comparison(
        insufficient,
        0.95,
        window=MIN_POSITIVE_GAPS,
        minimum=1,
        positive_only=True,
    )
    slow = slow_rolling_comparison(
        insufficient,
        0.95,
        window=MIN_POSITIVE_GAPS,
        minimum=1,
        positive_only=True,
    )
    assert np.array_equal(fast[0], slow[0])
    assert np.array_equal(fast[1], slow[1])
    assert not slow[1][-1]


def test_positive_gap_threshold_excludes_nonpositive_and_future_values() -> None:
    history = np.arange(1, MIN_POSITIVE_GAPS + 1, dtype=float)
    values = np.concatenate([history, np.array([951.0, 10_000.0])])

    first_result, first_eligible = rolling_comparison(
        values,
        0.95,
        window=MIN_POSITIVE_GAPS,
        positive_only=True,
    )

    changed = values.copy()
    changed[-1] = -10_000.0
    second_result, second_eligible = rolling_comparison(
        changed,
        0.95,
        window=MIN_POSITIVE_GAPS,
        positive_only=True,
    )

    # A future observation cannot alter the preceding decision.
    assert first_eligible[-2] and second_eligible[-2]
    assert first_result[-2] == second_result[-2]
