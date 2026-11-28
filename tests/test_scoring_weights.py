import pytest
from fastapi import HTTPException

from app import _parse_scoring_weights


def test_scoring_weights_are_optional_and_accept_valid_non_negative_values():
    assert _parse_scoring_weights("") is None
    assert _parse_scoring_weights('{"cost": 60, "completeness": 20, "timeline": 10, "terms": 5, "risk": 5}') == {
        "cost": 60.0,
        "completeness": 20.0,
        "timeline": 10.0,
        "terms": 5.0,
        "risk": 5.0,
    }


@pytest.mark.parametrize("raw", [
    "not-json",
    "[]",
    '{"unknown": 1}',
    '{"cost": -1}',
    '{"cost": "NaN"}',
    '{"cost": 0, "completeness": 0, "timeline": 0, "terms": 0, "risk": 0}',
])
def test_scoring_weights_reject_invalid_or_all_zero_values(raw):
    with pytest.raises(HTTPException) as exc:
        _parse_scoring_weights(raw)
    assert exc.value.status_code == 422
