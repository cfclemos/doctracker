"""Totals of an invoice."""


def total(prices: list[float]) -> float:
    """Add up the prices of an invoice.

    Args:
        prices: Price of each item.

    Returns:
        The sum of the prices.
    """
    return sum(prices)
