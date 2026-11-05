"""The shop's pages through the Django models: each use of a model reaches its table."""

from django.http import HttpRequest, JsonResponse

from .models import Customer, Order


def customer_orders(request: HttpRequest, customer_id: int) -> JsonResponse:
    """The orders of a customer, newest first."""
    customer = Customer.objects.get(pk=customer_id)
    orders = Order.objects.filter(customer=customer).order_by("-placed_at")
    return JsonResponse({"customer": customer.full_name, "orders": [order.id for order in orders]})


def customers_by_phone(request: HttpRequest) -> JsonResponse:
    """The customers who gave a phone."""
    return JsonResponse({"customers": list(Customer.objects.exclude(phone=None).values_list(Customer.email.field.name, flat=True))})
