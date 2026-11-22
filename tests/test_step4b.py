"""Offline tests for the climate tool."""
from datetime import date

import pytest

import tools.climate as climate
from tools.climate import ClimateError, get_climate, summarize_daily


def test_summarize_ignores_missing_days():
    daily = {"temperature_2m_mean": [20.0, None, 22.0], "precipitation_sum": [0.0, 5.0, None]}
    s = summarize_daily(daily, "2024-01-01", "2024-01-03")
    assert s.mean_temp_c == 21.0
    assert s.total_precip_mm == 5.0
    assert s.rainy_days == 1
    assert s.days_with_data == 2


def test_summarize_without_data_raises():
    with pytest.raises(ClimateError):
        summarize_daily({"temperature_2m_mean": [None], "precipitation_sum": [None]}, "a", "b")


def test_rejects_reversed_dates_and_recent_dates():
    with pytest.raises(ClimateError):
        get_climate(35.2, -3.9, date(2024, 2, 1), date(2024, 1, 1))
    with pytest.raises(ClimateError):
        get_climate(35.2, -3.9, date(2024, 1, 1), date.today())


def test_get_climate_parses_api_response(monkeypatch):
    get_climate.cache_clear()

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"daily": {"time": ["2023-09-01", "2023-09-02"],
                              "temperature_2m_mean": [24.0, 26.0],
                              "precipitation_sum": [0.0, 12.5]}}

    monkeypatch.setattr(climate.requests, "get", lambda *a, **k: FakeResponse())
    s = get_climate(35.2, -3.9, date(2023, 9, 1), date(2023, 9, 2))
    assert (s.mean_temp_c, s.total_precip_mm, s.rainy_days) == (25.0, 12.5, 1)
