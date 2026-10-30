"""The acme core schema as Django models: the state after the five migrations."""

from django.db import models


class Category(models.Model):
    """Categories of products, as a tree."""

    id = models.AutoField(primary_key=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE)
    name = models.TextField()
    slug = models.TextField(unique=True)

    class Meta:
        db_table = "categories"
        db_table_comment = "Categories of products, as a tree."


class Product(models.Model):
    """What the shop sells."""

    id = models.AutoField(primary_key=True)
    sku = models.TextField(unique=True)
    name = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    active = models.BooleanField(default=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = "products"
        db_table_comment = "What the shop sells."
        constraints = [models.CheckConstraint(condition=models.Q(price__gte=0), name="products_price_check")]


class Customer(models.Model):
    """People who buy at the shop."""

    full_name = models.TextField()
    email = models.TextField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    cpf = models.CharField(max_length=14, unique=True, null=True, blank=True)
    phone = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "customers"
        db_table_comment = "People who buy at the shop."


class Order(models.Model):
    """An order of a customer."""

    class Status(models.TextChoices):
        """Where an order is in its life."""

        DRAFT = "draft"
        PLACED = "placed"
        PAID = "paid"
        SHIPPED = "shipped"
        CANCELLED = "cancelled"

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    status = models.TextField(choices=Status.choices, default=Status.DRAFT)
    placed_at = models.DateTimeField(null=True, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = "orders"
        db_table_comment = "An order of a customer."
        indexes = [models.Index(fields=["customer"], name="orders_customer")]
        constraints = [models.CheckConstraint(condition=models.Q(status__in=["draft", "placed", "paid", "shipped", "cancelled"]),
                                              name="orders_status_check")]


class OrderItem(models.Model):
    """The lines of an order."""

    pk = models.CompositePrimaryKey("order", "line")
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    line = models.SmallIntegerField()
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "order_items"
        db_table_comment = "The lines of an order."
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="order_items_quantity_check")]


class Payment(models.Model):
    """Money received for an order."""

    class Method(models.TextChoices):
        """How it was paid."""

        PIX = "pix"
        CARD = "card"
        BOLETO = "boleto"

    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    paid_at = models.DateTimeField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.TextField(choices=Method.choices)

    class Meta:
        db_table = "payments"
        db_table_comment = "Money received for an order."
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="payments_amount_check"),
                       models.CheckConstraint(condition=models.Q(method__in=["pix", "card", "boleto"]), name="payments_method_check")]
