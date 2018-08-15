from django.db import models


class ReferencedStripeObject(models.Model):
    reference = models.CharField(max_length=190, db_index=True, unique=True)
    order = models.ForeignKey('pretixbase.Order', on_delete=models.CASCADE)
    payment = models.ForeignKey('pretixbase.OrderPayment', null=True, blank=True, on_delete=models.CASCADE)


class RegisteredApplePayDomain(models.Model):
    domain = models.CharField(max_length=190)
    account = models.CharField(max_length=190)
