"""The score -> Best/Medium/No mapping."""

import pytest

from backend.models import Fit
from backend.services import fit_for


@pytest.mark.parametrize(
    "score,expected",
    [
        (100, Fit.BEST),
        (75, Fit.BEST),   # boundary: FIT_BEST_MIN is inclusive
        (74, Fit.MEDIUM),
        (45, Fit.MEDIUM), # boundary: FIT_MEDIUM_MIN is inclusive
        (44, Fit.NO),
        (0, Fit.NO),
    ],
)
def test_fit_thresholds(score, expected):
    assert fit_for(score) == expected
