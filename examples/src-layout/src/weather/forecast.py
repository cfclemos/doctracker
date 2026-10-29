"""Fetch and describe the forecast of a city."""

from dataclasses import dataclass


@dataclass
class Forecast:
    """The forecast of one city.

    Attributes:
        city: City name.
        temperature: Temperature in degrees Celsius.
    """

    city: str
    temperature: float


def get_forecast(city: str) -> Forecast:
    """Fetch the forecast for a city.

    Args:
        city: City name, e.g. `Lisbon`.

    Returns:
        The forecast of the city.
    """
    return Forecast(city, _temperature_of(city))


def _temperature_of(city: str) -> float:
    """A made-up temperature for a city."""
    return 15.0 + len(city)
