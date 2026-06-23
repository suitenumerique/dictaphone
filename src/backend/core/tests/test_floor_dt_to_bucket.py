"""
Test utils.floor_df_to_bucket
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.utils import floor_dt_to_bucket


def test_datetime_equal_to_reference_uses_last_bucket_window():
    """A datetime equal to the reference should map to the last window start."""
    reference = datetime(2026, 6, 23, 12, 10, 0)
    dt = reference
    expected = datetime(2026, 6, 23, 12, 7, 30)

    assert floor_dt_to_bucket(dt, 150, reference_dt=reference) == expected


def test_datetime_within_last_bucket():
    """Datetimes in the last window should map to that window start."""
    reference = datetime(2026, 6, 23, 12, 10, 0)
    dt = datetime(2026, 6, 23, 12, 9, 55)
    expected = datetime(2026, 6, 23, 12, 7, 30)

    assert floor_dt_to_bucket(dt, 150, reference_dt=reference) == expected


def test_datetime_older_than_last_bucket():
    """Datetimes older than one window should map to previous bucket starts."""
    reference = datetime(2026, 6, 23, 12, 10, 0)
    dt = datetime(2026, 6, 23, 12, 4, 59)
    expected = datetime(2026, 6, 23, 12, 2, 30)

    assert floor_dt_to_bucket(dt, 150, reference_dt=reference) == expected


def test_boundary_included_in_last_bucket():
    """The lower boundary of the last bucket belongs to the last bucket."""
    reference = datetime(2026, 6, 23, 12, 10, 0)
    dt = datetime(2026, 6, 23, 12, 5, 0)
    expected = datetime(2026, 6, 23, 12, 5, 0)

    assert floor_dt_to_bucket(dt, 300, reference_dt=reference) == expected


def test_timezone_aware_datetime():
    """Timezone-aware datetimes should be floored correctly."""
    tz = timezone(timedelta(hours=2))
    reference = datetime(2026, 6, 23, 12, 10, 0, tzinfo=tz)
    dt = datetime(2026, 6, 23, 12, 8, 55, tzinfo=tz)
    expected = datetime(2026, 6, 23, 12, 7, 30, tzinfo=tz)

    assert floor_dt_to_bucket(dt, 150, reference_dt=reference) == expected


def test_zero_bucket_raises():
    """A bucket size of zero should raise an exception."""
    with pytest.raises(ZeroDivisionError):
        floor_dt_to_bucket(datetime.now(), 0, reference_dt=datetime.now())
