"""Step 2: customers and their orders."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Create customers, orders and order items."""

    dependencies = [("shop", "0001_catalog")]
    operations = [
        migrations.CreateModel(
            name="Customer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.TextField()),
                ("email", models.TextField(unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "customers", "db_table_comment": "People who buy at the shop."},
        ),
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.TextField(choices=[("draft", "Draft"), ("placed", "Placed"), ("paid", "Paid"), ("shipped", "Shipped"),
                                                     ("cancelled", "Cancelled")], default="draft")),
                ("placed_at", models.DateTimeField(blank=True, null=True)),
                ("total", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("customer", models.ForeignKey(on_delete=models.deletion.PROTECT, to="shop.customer")),
            ],
            options={
                "db_table": "orders",
                "db_table_comment": "An order of a customer.",
                "constraints": [models.CheckConstraint(condition=models.Q(("status__in", ["draft", "placed", "paid", "shipped", "cancelled"])),
                                                       name="orders_status_check")],
            },
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[
                ("pk", models.CompositePrimaryKey("order", "line", blank=True, editable=False, primary_key=True, serialize=False)),
                ("line", models.SmallIntegerField()),
                ("quantity", models.IntegerField()),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("order", models.ForeignKey(on_delete=models.deletion.CASCADE, to="shop.order")),
                ("product", models.ForeignKey(on_delete=models.deletion.PROTECT, to="shop.product")),
            ],
            options={
                "db_table": "order_items",
                "db_table_comment": "The lines of an order.",
                "constraints": [models.CheckConstraint(condition=models.Q(("quantity__gt", 0)), name="order_items_quantity_check")],
            },
        ),
    ]
