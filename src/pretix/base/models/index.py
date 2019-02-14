from django.db import models

DELIMITER = "\x1F"


class OrderSearchIndex(models.Model):
    order = models.ForeignKey('Order', unique=True, null=False, on_delete=models.CASCADE)
    event = models.ForeignKey('Event', null=False, on_delete=models.CASCADE)
    organizer = models.ForeignKey('Organizer', null=False, on_delete=models.CASCADE)
    search_body = models.TextField()
    payment_providers = models.TextField()
