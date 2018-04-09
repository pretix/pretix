from django.db import models


class Thumbnail(models.Model):
    source = models.CharField(max_length=255)
    size = models.CharField(max_length=255)
    thumb = models.FileField(upload_to='pub/thumbs/', max_length=255)

    class Meta:
        unique_together = (('source', 'size'),)
