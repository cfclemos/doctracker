"""The pages of the shop."""

from acme.billing.invoice import total


def invoice_page(prices: list[float]) -> str:
    """Render the page of an invoice.

    Args:
        prices: Price of each item.

    Returns:
        The name of the template and the total, as text.
    """
    return f"page.html: {total(prices)}"
