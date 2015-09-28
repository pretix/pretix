# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0017_order_guest_locale'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventlock',
            name='token',
            field=models.UUIDField(default=uuid.uuid4),
        ),
    ]
