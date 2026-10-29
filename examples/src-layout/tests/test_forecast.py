"""Tests of the forecast."""

from weather import get_forecast


def test_forecast_names_the_city() -> None:
    """The forecast keeps the city asked for."""
    assert get_forecast("Lisbon").city == "Lisbon"
