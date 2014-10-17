from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.utils.encoding import force_text

from tixlbase.models import ItemVariation, PropertyValue


class TolerantFormsetModelForm(forms.ModelForm):
    def has_changed(self):
        """
        Returns True if data differs from initial. Contrary to the default
        implementation, the ORDER field is being ignored.
        """
        for name, field in self.fields.items():
            if name == 'ORDER':
                continue
            prefixed_name = self.add_prefix(name)
            data_value = field.widget.value_from_datadict(self.data, self.files, prefixed_name)
            if not field.show_hidden_initial:
                initial_value = self.initial.get(name, field.initial)
                if callable(initial_value):
                    initial_value = initial_value()
            else:
                initial_prefixed_name = self.add_initial_prefix(name)
                hidden_widget = field.hidden_widget()
                try:
                    initial_value = field.to_python(hidden_widget.value_from_datadict(
                        self.data, self.files, initial_prefixed_name))
                except forms.ValidationError:
                    # Always assume data has changed if validation fails.
                    self._changed_data.append(name)
                    continue
            # We're using a private API of Django here. This is not nice, but no problem as it seems
            # like this will become a public API in Django 1.7.
            if field._has_changed(initial_value, data_value):
                return True
        return False


class RestrictionForm(TolerantFormsetModelForm):
    """
    The restriction form provides useful functionality for all forms
    representing a restriction instance. To be concret, this form does
    the necessary magic to make the 'variations' field work correctly
     and look beautiful.
    """

    def __init__(self, *args, **kwargs):
        if 'item' in kwargs:
            self.item = kwargs['item']
            del kwargs['item']
            super().__init__(*args, **kwargs)
            if 'variations' in self.fields and isinstance(self.fields['variations'], VariationsField):
                self.fields['variations'].set_item(self.item)


class RestrictionInlineFormset(forms.BaseInlineFormSet):
    """
    This is the base class you should use for any formset you return
    from a ``restriction_formset`` signal receiver that contains
    RestrictionForm objects as its forms, as it correcly handles the
    necessary item parameter for the RestrictionForm. While this could
    be achieved with a regular formset, this also adds a
    ``initialized_empty_form`` method which is the only way to correctly
    render a working empty form for a JavaScript-enabled restriction formset.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def initialized_empty_form(self):
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            item=self.instance
        )
        self.add_fields(form, None)
        return form

    def _construct_form(self, i, **kwargs):
        kwargs['item'] = self.instance
        return super()._construct_form(i, **kwargs)

    class Meta:
        exclude = ['item']


class VariationsField(forms.ModelMultipleChoiceField):
    """
    This form field is intended to be used to let the user select a
    variation of a certain item, for example in a restriction plugin.

    As this field expects the non-standard keyword parameter ``item``
    at initialization time, this is field is normally named ``variations``
    and lives inside a ``tixlcontrol.views.forms.RestrictionForm``, which
    does some magic to provide this parameter.
    """

    def __init__(self, *args, item=None, **kwargs):
        self.item = item
        super().__init__(*args, **kwargs)

    def set_item(self, item):
        self.item = item
        self._set_choices(self._get_choices())

    def _get_choices(self):
        """
        We can't use a normal QuerySet as there theoretically might be
        two types of variations: Some who already have a ItemVariation
        object associated with tham and some who don't. We therefore use
        the item's ``get_all_variations`` method. In the first case, we
        use the ItemVariation objects primary key as our choice, key,
        in the latter case we use a string constructed from the values
        (see VariationDict.key() for implementation details).
        """
        if self.item is None:
            return ()
        variations = self.item.get_all_variations()
        return (
            (
                v['variation'].pk if 'variation' in v else v.key(),
                v
            ) for v in variations
        )

    def clean(self, value):
        """
        At cleaning time, we have to clean up the mess we produced with our
        _get_choices implementation. In the case of ItemVariation object ids
        we don't to anything to them, but if one of the selected items is a
        list of PropertyValue objects (see _get_choices), we need to create
        a new ItemVariation object for this combination and then add this to
        our list of selected items.
        """
        if self.item is None:
            raise ValueError(
                "VariationsField object was not properly initialized. Please"
                "use a tixlcontrol.views.forms.RestrictionForm form instead of"
                "a plain Django ModelForm"
            )

        # Standard validation foo
        if self.required and not value:
            raise ValidationError(self.error_messages['required'], code='required')
        elif not self.required and not value:
            return self.queryset.none()
        if not isinstance(value, (list, tuple)):
            raise ValidationError(self.error_messages['list'], code='list')

        # Build up a cache of variations having an ItemVariation object
        # For implementation details, see ItemVariation.get_all_variations()
        # which uses a very similar method
        all_variations = self.item.variations.all().prefetch_related("values")
        variations_cache = {}
        for var in all_variations:
            key = []
            for v in var.values.all():
                key.append((v.prop_id, v.pk))
            key = tuple(sorted(key))
            variations_cache[key] = var.pk

        cleaned_value = []

        # Wrap this in a transaction to prevent strange database state if we
        # get a ValidationError half-way through
        with transaction.atomic():
            for pk in value:
                if ":" in pk:
                    # A combination of PropertyValues was given

                    # Hash the combination in the same way as in our cache above
                    key = []
                    for pair in pk.split(","):
                        key.append(tuple([int(i) for i in pair.split(":")]))
                    key = tuple(sorted(key))

                    if key in variations_cache:
                        # An ItemVariation object already exists for this variation,
                        # so use this. (This might occur if the variation object was
                        # created _after_ the user loaded the form but _before_ he
                        # submitted it.)
                        cleaned_value.append(str(variations_cache[key]))
                        continue

                    # No ItemVariation present, create one!
                    var = ItemVariation()
                    var.item = self.item
                    var.save()
                    # Add the values to the ItemVariation object
                    for pair in pk.split(","):
                        prop, value = pair.split(":")
                        try:
                            var.values.add(
                                PropertyValue.objects.get(
                                    pk=value,
                                    prop_pk=prop
                                )
                            )
                        except PropertyValue.DoesNotExist:
                            raise ValidationError(
                                self.error_messages['invalid_pk_value'],
                                code='invalid_pk_value',
                                params={'pk': value},
                            )
                    variations_cache[key] = var.pk
                    cleaned_value.append(str(var.pk))
                else:
                    # An ItemVariation id was given
                    cleaned_value.append(pk)

        qs = ItemVariation.objects.filter(item=self.item, pk__in=cleaned_value)

        # Re-check for consistency
        pks = set(force_text(getattr(o, "pk")) for o in qs)
        for val in cleaned_value:
            if force_text(val) not in pks:
                raise ValidationError(
                    self.error_messages['invalid_choice'],
                    code='invalid_choice',
                    params={'value': val},
                )

        # Since this overrides the inherited ModelChoiceField.clean
        # we run custom validators here
        self.run_validators(cleaned_value)
        return qs

    choices = property(_get_choices, forms.ChoiceField._set_choices)
