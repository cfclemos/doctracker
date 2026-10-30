"""Step 3: more about customers, and the cost of each product."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add the CPF, the phone and the cost."""

    dependencies = [("shop", "0002_sales")]
    operations = [
        migrations.AddField(model_name="customer", name="cpf", field=models.CharField(blank=True, max_length=14, null=True, unique=True)),
        migrations.AddField(model_name="customer", name="phone", field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name="product", name="cost", field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
    ]
