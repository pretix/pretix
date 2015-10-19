import os
from functools import partial
from itertools import product

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import (
    BaseInlineFormSet, BaseModelFormSet, ModelForm, modelformset_factory,
)
from django.forms.widgets import flatatt
from django.utils.encoding import force_text
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms import VersionedModelForm
from pretix.base.models import Item, ItemVariation


class I18nInlineFormSet(BaseInlineFormSet):
    """
    This is equivalent to a normal BaseInlineFormset, but cares for the special needs
    of I18nForms (see there for more information).
    """

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['event'] = self.event
        return super()._construct_form(i, **kwargs)


class I18nFormSet(BaseModelFormSet):
    """
    This is equivalent to a normal BaseModelFormset, but cares for the special needs
    of I18nForms (see there for more information).
    """

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['event'] = self.event
        return super()._construct_form(i, **kwargs)

    @property
    def empty_form(self):
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            event=self.event
        )
        self.add_fields(form, None)
        return form


class TolerantFormsetModelForm(VersionedModelForm):
    """
    This is equivalent to a normal VersionedModelForm, but works around a problem that
    arises when the form is used inside a FormSet with can_order=True and django-formset-js
    enabled. In this configuration, even empty "extra" forms might have an ORDER value
    sent and Django marks the form as empty and raises validation errors because the other
    fields have not been filled.
    """

    def has_changed(self) -> bool:
        """
        Returns True if data differs from initial. Contrary to the default
        implementation, the ORDER field is being ignored.
        """
        for name, field in self.fields.items():
            if name == 'ORDER' or name == 'id':
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
            # like this will become a public API in future Django.
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

    def __init__(self, data=None, files=None, instance=None,
                 save_as_new=False, prefix=None, queryset=None, **kwargs):
        super().__init__(
            data, files, instance, save_as_new, prefix, queryset, **kwargs
        )
        if isinstance(self.instance, Item):
            self.queryset = self.queryset.as_of().prefetch_related("variations")

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


def selector(values, prop):
    # Given an iterable of PropertyValue objects, this will return a
    # list of their primary keys, ordered by the primary keys of the
    # properties they belong to EXCEPT the value for the property prop2.
    # We'll see later why we need this.
    return [
        v.identity for v in sorted(values, key=lambda v: v.prop.identity)
        if v.prop.identity != prop.identity
    ]


def sort(v, prop):
    # Given a list of variations, this will sort them by their position
    # on the x-axis
    return v[prop.identity].sortkey


class VariationsFieldRenderer(forms.widgets.CheckboxFieldRenderer):
    """
    This is the default renderer for a VariationsField. Based on the choice input class
    this renders a list or a matrix of checkboxes/radio buttons/...
    """

    def __init__(self, name, value, attrs, choices):
        self.name = name
        self.value = value
        self.attrs = attrs
        self.choices = choices

    def render(self):
        """
        Outputs a grid for this set of choice fields.
        """
        if len(self.choices) == 0:
            raise ValueError("Can't handle empty lists")

        variations = []
        for key, value in self.choices:
            value['key'] = key
            variations.append(value)

        properties = [v.prop for v in variations[0].relevant_values()]
        dimension = len(properties)

        id_ = self.attrs.get('id', None)
        start_tag = format_html('<div class="variations" id="{0}">', id_) if id_ else '<div class="variations">'
        output = [start_tag]

        # TODO: This is very duplicate to pretixcontrol.views.item.ItemVariations.get_forms()
        # Find a common abstraction to avoid the repetition.
        if dimension == 0:
            output.append(format_html('<em>{0}</em>', _("not applicable")))
        elif dimension == 1:
            output = self.render_1d(output, variations, properties)
        else:
            output = self.render_nd(output, variations, properties)
        output.append(
            ('<div class="help-block"><a href="#" class="variations-select-all">{0}</a> · '
             '<a href="#" class="variations-select-none">{1}</a></div></div>').format(
                _("Select all"),
                _("Deselect all")
            )
        )
        return mark_safe('\n'.join(output))

    def render_1d(self, output, variations, properties):
        output.append('<ul>')
        for i, variation in enumerate(variations):
            final_attrs = dict(
                self.attrs.copy(), type=self.choice_input_class.input_type,
                name=self.name, value=variation['key']
            )
            if variation['key'] in self.value:
                final_attrs['checked'] = 'checked'
            w = self.choice_input_class(
                self.name, self.value, self.attrs.copy(),
                (variation['key'], variation[properties[0].identity].value),
                i
            )
            output.append(format_html('<li>{0}</li>', force_text(w)))
        output.append('</ul>')
        return output

    def render_nd(self, output, variations, properties):
        # prop1 is the property on all the grid's y-axes
        prop1 = properties[0]
        prop1v = list(prop1.values.current.all())
        # prop2 is the property on all the grid's x-axes
        prop2 = properties[1]
        prop2v = list(prop2.values.current.all())

        # We now iterate over the cartesian product of all the other
        # properties which are NOT on the axes of the grid because we
        # create one grid for any combination of them.
        for gridrow in product(*[prop.values.current.all() for prop in properties[2:]]):
            if len(gridrow) > 0:
                output.append('<strong>')
                output.append(", ".join([str(value.value) for value in gridrow]))
                output.append('</strong>')
            output.append('<table class="table"><thead><tr><th></th>')
            for val2 in prop2v:
                output.append(format_html('<th>{0}</th>', val2.value))
            output.append('</thead><tbody>')
            for val1 in prop1v:
                output.append(format_html('<tr><th>{0}</th>', val1.value))
                # We are now inside one of the rows of the grid and have to
                # select the variations to display in this row. In order to
                # achieve this, we use the 'selector' lambda defined above.
                # It gives us a normalized, comparable version of a set of
                # PropertyValue objects. In this case, we compute the
                # selector of our row as the selector of the sum of the
                # values defining our grind and the value defining our row.
                selection = selector(gridrow + (val1,), prop2)
                # We now iterate over all variations who generate the same
                # selector as 'selection'.
                filtered = [v for v in variations if selector(v.relevant_values(), prop2) == selection]
                for variation in sorted(filtered, key=partial(sort, prop=prop2)):
                    final_attrs = dict(
                        self.attrs.copy(), type=self.choice_input_class.input_type,
                        name=self.name, value=variation['key']
                    )
                    if variation['key'] in self.value:
                        final_attrs['checked'] = 'checked'
                    output.append(format_html('<td><label><input{0} /></label></td>', flatatt(final_attrs)))
                output.append('</td>')
            output.append('</tbody></table>')
        return output


class VariationsCheckboxRenderer(VariationsFieldRenderer):
    """
    This is the same as VariationsFieldRenderer but with the choice input class
    forced to checkboxes
    """
    choice_input_class = forms.widgets.CheckboxChoiceInput


class VariationsSelectMultiple(forms.CheckboxSelectMultiple):
    """
    This is the default widget for a VariationsField
    """
    renderer = VariationsCheckboxRenderer
    _empty_value = []


class VariationsField(forms.ModelMultipleChoiceField):
    """
    This form field is intended to be used to let the user select a
    variation of a certain item, for example in a restriction plugin.

    As this field expects the non-standard keyword parameter ``item``
    at initialization time, this is field is normally named ``variations``
    and lives inside a ``pretixcontrol.views.forms.RestrictionForm``, which
    does some magic to provide this parameter.
    """

    def __init__(self, *args, item=None, **kwargs):
        self.item = item
        if 'widget' not in args or kwargs['widget'] is None:
            kwargs['widget'] = VariationsSelectMultiple
        super().__init__(*args, **kwargs)

    def set_item(self, item: Item):
        assert isinstance(item, Item)
        self.item = item
        self._set_choices(self._get_choices())

    def _get_choices(self) -> "list[(str, VariationDict)]":
        """
        We can't use a normal QuerySet as there theoretically might be
        two types of variations: Some who already have a ItemVariation
        object associated with them and some who don't. We therefore use
        the item's ``get_all_variations`` method. In the first case, we
        use the ItemVariation objects primary key as our choice, key,
        in the latter case we use a string constructed from the values
        (see VariationDict.key() for implementation details).
        """
        if self.item is None:
            return ()
        variations = self.item.get_all_variations(use_cache=True)
        return (
            (
                v['variation'].identity if 'variation' in v else v.key(),
                v
            ) for v in variations
        )

    def clean(self, value: "list[int]"):
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
                "use a pretixcontrol.views.forms.RestrictionForm form instead of"
                "a plain Django ModelForm"
            )

        # Standard validation foo
        if self.required and not value:
            raise ValidationError(self.error_messages['required'], code='required')
        elif not self.required and not value:
            return []
        if not isinstance(value, (list, tuple)):
            raise ValidationError(self.error_messages['list'], code='list')

        cleaned_value = self._clean_value(value)

        qs = self.item.variations.current.filter(identity__in=cleaned_value)

        # Re-check for consistency
        pks = set(force_text(getattr(o, "identity")) for o in qs)
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

    def _clean_value(self, value):
        # Build up a cache of variations having an ItemVariation object
        # For implementation details, see ItemVariation.get_all_variations()
        # which uses a very similar method
        all_variations = self.item.variations.all().prefetch_related("values")
        variations_cache = {
            var.to_variation_dict().identify(): var.identity for var in all_variations
        }

        cleaned_value = []

        # Wrap this in a transaction to prevent strange database state if we
        # get a ValidationError half-way through
        with transaction.atomic():
            for pk in value:
                if ":" in pk:
                    # A combination of PropertyValues was given

                    # Hash the combination in the same way as in our cache above
                    key = ",".join([pair.split(":")[1] for pair in sorted(pk.split(","))])

                    if key in variations_cache:
                        # An ItemVariation object already exists for this variation,
                        # so use this. (This might occur if the variation object was
                        # created _after_ the user loaded the form but _before_ he
                        # submitted it.)
                        cleaned_value.append(str(variations_cache[key]))
                        continue

                    # No ItemVariation present, create one!
                    var = ItemVariation()
                    var.item_id = self.item.identity
                    var.save()
                    # Add the values to the ItemVariation object
                    try:
                        var.add_values_from_string(pk)
                    except:
                        raise ValidationError(
                            self.error_messages['invalid_pk_value'],
                            code='invalid_pk_value',
                            params={'pk': value},
                        )
                    variations_cache[key] = var.identity
                    cleaned_value.append(str(var.identity))
                else:
                    # An ItemVariation id was given
                    cleaned_value.append(pk)
        return cleaned_value

    choices = property(_get_choices, forms.ChoiceField._set_choices)


class ExtFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        ext_whitelist = kwargs.pop("ext_whitelist")
        self.ext_whitelist = [i.lower() for i in ext_whitelist]
        super().__init__(*args, **kwargs)

    def clean(self, *args, **kwargs):
        data = super().clean(*args, **kwargs)
        if data:
            filename = data.name
            ext = os.path.splitext(filename)[1]
            ext = ext.lower()
            if ext not in self.ext_whitelist:
                raise forms.ValidationError(_("Filetype not allowed!"))
        return data


class BaseNestedFormset(I18nFormSet):

    def add_fields(self, form, index):
        # allow the super class to create the fields as usual
        super().add_fields(form, index)

        form.nested = []
        for f in self.nested_formset_class:
            inner_formset = f(
                instance=form.instance,
                data=form.data if form.is_bound else None,
                prefix='%s-%s' % (form.prefix, f.get_default_prefix()),
                queryset=form.instance.values.all(),
                event=self.event
            )
            form.nested.append(inner_formset)

    def is_valid(self):
        result = super(BaseNestedFormset, self).is_valid()

        if self.is_bound:
            # look at any nested formsets, as well
            for form in self.forms:
                if not self._should_delete_form(form):
                    for n in form.nested:
                        result = result and n.is_valid()

        return result

    def save(self, commit=True):
        result = super(BaseNestedFormset, self).save(commit=commit)

        for form in self.forms:
            if not self._should_delete_form(form):
                for n in form.nested:
                    n.save(commit=commit)

        return result


def nestedformset_factory(model, nested_formset, form=ModelForm,
                          formset=BaseNestedFormset, fk_name=None, fields=None,
                          exclude=None, extra=3, can_order=False,
                          can_delete=True, max_num=None,
                          formfield_callback=None, widgets=None,
                          validate_max=False, localized_fields=None,
                          labels=None, help_texts=None, error_messages=None):
    kwargs = {
        'form': form,
        'formfield_callback': formfield_callback,
        'formset': formset,
        'extra': extra,
        'can_delete': can_delete,
        'can_order': can_order,
        'fields': fields,
        'exclude': exclude,
        'max_num': max_num,
        'widgets': widgets,
        'validate_max': validate_max,
        'localized_fields': localized_fields,
        'labels': labels,
        'help_texts': help_texts,
        'error_messages': error_messages,
    }

    nfs_class = modelformset_factory(model, **kwargs)
    nfs_class.nested_formset_class = []
    for f in nested_formset:
        nfs_class.nested_formset_class.append(f)
    return nfs_class


class NestedInnerI18nInlineFormSet(I18nFormSet):
    """A formset for child objects related to a parent."""

    def __init__(self, data=None, files=None, instance=None,
                 save_as_new=False, prefix=None, queryset=None, **kwargs):
        if instance is None:
            self.instance = self.fk.rel.to()
        else:
            self.instance = instance
        self.save_as_new = save_as_new
        if queryset is None:
            if self.instance is not None:
                queryset = getattr(self.instance, self.fk.related_query_name()).all()
            else:
                queryset = self.model._default_manager
        if self.instance.pk is not None:
            qs = queryset
        else:
            qs = self.model._default_manager.none()
        super().__init__(data, files, prefix=prefix, queryset=qs, **kwargs)

    @property
    def empty_form(self):
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__inner_prefix__'),
            empty_permitted=True,
            event=self.event
        )
        self.add_fields(form, None)
        return form
