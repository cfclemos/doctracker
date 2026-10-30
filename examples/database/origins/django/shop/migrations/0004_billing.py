"""Step 4: payments of the orders."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Create payments."""

    dependencies = [("shop", "0003_customer_details_and_cost")]
    operations = [
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("paid_at", models.DateTimeField()),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("method", models.TextField(choices=[("pix", "Pix"), ("card", "Card"), ("boleto", "Boleto")])),
                ("order", models.ForeignKey(on_delete=models.deletion.CASCADE, to="shop.order")),
            ],
            options={
                "db_table": "payments",
                "db_table_comment": "Money received for an order.",
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="payments_amount_check"),
                    models.CheckConstraint(condition=models.Q(("method__in", ["pix", "card", "boleto"])), name="payments_method_check"),
                ],
            },
        ),
    ]
