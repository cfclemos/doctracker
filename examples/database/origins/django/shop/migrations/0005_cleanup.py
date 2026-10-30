"""Step 5: a destructive change, a rename and an index (what a migration lint must flag)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Drop the description, rename the customer's name, index the orders by customer."""

    dependencies = [("shop", "0004_billing")]
    operations = [
        migrations.RemoveField(model_name="product", name="description"),
        migrations.RenameField(model_name="customer", old_name="name", new_name="full_name"),
        migrations.AddIndex(model_name="order", index=models.Index(fields=["customer"], name="orders_customer")),
    ]
