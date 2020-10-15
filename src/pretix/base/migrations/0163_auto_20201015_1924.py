# Generated by Django 3.0.10 on 2020-10-15 19:24

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0162_remove_seat_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='orderposition',
            name='secret',
            field=models.CharField(db_index=True, max_length=64),
        ),
        migrations.CreateModel(
            name='RevokedTicketSecret',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('secret', models.TextField(db_index=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='revoked_secrets', to='pretixbase.Event')),
                ('position', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revoked_secrets', to='pretixbase.OrderPosition')),
            ],
        ),
    ]
