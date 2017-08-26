from django.db import models


class ReferencedStripeObject(models.Model):
    reference = models.CharField(max_length=190, db_index=True, unique=True)
    order = models.ForeignKey('pretixbase.Order')
