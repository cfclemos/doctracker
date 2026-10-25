"""The documentation guide agents read through the MCP server."""

from importlib.resources import files

from doctracker.config import Config

EXAMPLES = {
    "google": '''def get_weather(city: str, units: str = "metric") -> Forecast:
    """Fetch the forecast for a city.

    Args:
        city: City name, e.g. `Lisbon`.
        units: `metric` or `imperial`.

    Returns:
        Forecast data for the city.

    Raises:
        CityNotFound: When the city is unknown.

    Examples:
        >>> get_weather("Lisbon").temperature
        21.5
    """''',
    "numpy": '''def get_weather(city: str, units: str = "metric") -> Forecast:
    """Fetch the forecast for a city.

    Parameters
    ----------
    city
        City name, e.g. `Lisbon`.
    units
        `metric` or `imperial`.

    Returns
    -------
    Forecast
        Forecast data for the city.

    Raises
    ------
    CityNotFound
        When the city is unknown.

    Examples
    --------
    >>> get_weather("Lisbon").temperature
    21.5
    """''',
    "sphinx": '''def get_weather(city: str, units: str = "metric") -> Forecast:
    """Fetch the forecast for a city.

    :param city: City name, e.g. `Lisbon`.
    :param units: `metric` or `imperial`.
    :return: Forecast data for the city.
    :raises CityNotFound: When the city is unknown.
    """''',
}


def documentation_guide(config: Config) -> str:
    """The guide in Markdown, filled in with this project's settings."""
    template = files("doctracker.server").joinpath("guide.md").read_text(encoding="utf-8")
    return template.format(
        docstring_style=config.docstring_style,
        private_members="shown in the wiki" if config.show_private else "hidden from the wiki",
        example=EXAMPLES.get(config.docstring_style, EXAMPLES["google"]),
    )
