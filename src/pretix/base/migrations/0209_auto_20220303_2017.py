# Generated by Django 3.2.2 on 2022-03-03 20:17

from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models

import pretix.base.models.base
import pretix.base.models.fields


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0208_auto_20220214_1632'),
    ]

    operations = [
        migrations.AddField(
            model_name='cartposition',
            name='custom_price_input',
            field=models.DecimalField(decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='custom_price_input_is_net',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='line_price_gross',
            field=models.DecimalField(decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='listed_price',
            field=models.DecimalField(decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='price_after_voucher',
            field=models.DecimalField(decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='tax_rate',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=7),
        ),
        migrations.CreateModel(
            name='Discount',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('active', models.BooleanField(default=True)),
                ('internal_name', models.CharField(max_length=255)),
                ('position', models.PositiveIntegerField(default=0)),
                ('sales_channels', pretix.base.models.fields.MultiStringField(default=['web'])),
                ('available_from', models.DateTimeField(blank=True, null=True)),
                ('available_until', models.DateTimeField(blank=True, null=True)),
                ('subevent_mode', models.CharField(max_length=50, default='mixed')),
                ('condition_all_products', models.BooleanField(default=True)),
                ('condition_min_count', models.PositiveIntegerField(default=0)),
                ('condition_min_value', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10)),
                ('benefit_discount_matching_percent', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10)),
                ('benefit_only_apply_to_cheapest_n_matches', models.PositiveIntegerField(null=True)),
                ('condition_limit_products', models.ManyToManyField(to='pretixbase.Item')),
                ('condition_apply_to_addons', models.BooleanField(default=True)),
                        ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='discounts', to='pretixbase.event')),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model, pretix.base.models.base.LoggingMixin),
        ),
        migrations.AddField(
            model_name='cartposition',
            name='discount',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.RESTRICT, to='pretixbase.discount'),
        ),
        migrations.AddField(
            model_name='orderposition',
            name='discount',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.RESTRICT, to='pretixbase.discount'),
        ),
        migrations.AddField(
            model_name='orderposition',
            name='voucher_budget_use',
            field=models.DecimalField(decimal_places=2, max_digits=10, null=True),
        ),
    ]
