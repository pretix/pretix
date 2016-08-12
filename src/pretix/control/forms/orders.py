from django import forms
from django.db import models

from pretix.base.forms import I18nModelForm
from pretix.base.models import Order


class ExtendForm(I18nModelForm):
    class Meta:
        model = Order
        fields = ['expires']


class ExporterForm(forms.Form):

    def clean(self):
        data = super().clean()

        for k, v in data.items():
            if isinstance(v, models.Model):
                data[k] = v.pk
            elif isinstance(v, models.QuerySet):
                data[k] = [m.pk for m in v]

        return data


class CommentForm(I18nModelForm):
    class Meta:
        model = Order
        fields = ['comment']
        widgets = {
            'comment': forms.Textarea(attrs={
                'rows': 3,
                'class': 'helper-width-100',
            }),
        }
