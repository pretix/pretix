from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("pretixbase", "0245_discount_benefit_products"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerSmsPreference",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "sms_opt_in",
                    models.BooleanField(
                        default=False,
                    ),
                ),
                (
                    "last_changed",
                    models.DateTimeField(
                        auto_now=True,
                    ),
                ),
                (
                    "customer",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        related_name="sms_preference",
                        to="pretixbase.customer",
                    ),
                ),
            ],
            options={
                "verbose_name": "Customer SMS preference",
                "verbose_name_plural": "Customer SMS preferences",
            },
        ),
    ]