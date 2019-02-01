from django import forms
from django.forms import Field
from django.forms.models import ModelChoiceIterator
from django.utils.translation import ugettext_lazy as _

from pretix.plugins.badges.models import BadgeItem, BadgeLayout


class BadgeLayoutForm(forms.ModelForm):
    class Meta:
        model = BadgeLayout
        fields = ('name',)


NoLayoutSingleton = BadgeLayout(pk='-')


class BadgeLayoutIterator(ModelChoiceIterator):

    def __iter__(self):
        yield ("-", _("(Do not print badges)"))
        yield from super().__iter__()

    def __len__(self):
        return super().__len__() + 1


class BadgeLayoutChoiceField(forms.ModelChoiceField):
    iterator = BadgeLayoutIterator

    def to_python(self, value):
        if value == '-':
            return NoLayoutSingleton
        return super().to_python(value)

    def validate(self, value):
        if value == '-':
            return '-'
        return Field.validate(self, value)


class BadgeItemForm(forms.ModelForm):
    layout = BadgeLayoutChoiceField(queryset=BadgeLayout.objects.none())

    class Meta:
        model = BadgeItem
        fields = ('layout',)
        exclude = ('layout',)

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['layout'].label = _('Badge layout')
        self.fields['layout'].empty_label = _('(Event default)')
        self.fields['layout'].queryset = event.badge_layouts.all()
        self.fields['layout'].required = False
        if self.instance.pk and not self.instance.layout_id:
            self.initial['layout'] = NoLayoutSingleton
        elif self.instance.layout:
            self.initial['layout'] = self.instance.layout

    def save(self, commit=True):
        if self.cleaned_data['layout'] is None:
            if self.instance.pk:
                self.instance.delete()
            else:
                return
        elif self.cleaned_data['layout'] is NoLayoutSingleton:
            self.instance.layout = None
            self.instance.save()
        else:
            self.instance.layout = self.cleaned_data['layout']
            return super().save(commit=commit)
