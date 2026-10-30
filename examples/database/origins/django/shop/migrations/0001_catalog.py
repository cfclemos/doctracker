"""Step 1: what the shop sells."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Create categories and products."""

    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.TextField()),
                ("slug", models.TextField(unique=True)),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE, to="shop.category")),
            ],
            options={"db_table": "categories", "db_table_comment": "Categories of products, as a tree."},
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("sku", models.TextField(unique=True)),
                ("name", models.TextField()),
                ("description", models.TextField(blank=True, null=True)),
                ("price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("active", models.BooleanField(default=True)),
                ("category", models.ForeignKey(on_delete=models.deletion.PROTECT, to="shop.category")),
            ],
            options={
                "db_table": "products",
                "db_table_comment": "What the shop sells.",
                "constraints": [models.CheckConstraint(condition=models.Q(("price__gte", 0)), name="products_price_check")],
            },
        ),
    ]
