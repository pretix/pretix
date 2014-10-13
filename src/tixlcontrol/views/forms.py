from django import forms


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
            if field._has_changed(initial_value, data_value):
                return True
        return False


class RestrictionForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        if 'item' in kwargs:
            self.item = kwargs['item']
            del kwargs['item']
            super().__init__(*args, **kwargs)
            if 'variations' in self.fields:
                self.fields['variations'] = VariationsField(item=self.item)


class RestrictionInlineFormset(forms.BaseInlineFormSet):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def initialized_empty_form(self):
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            item=self.instance
        )
        return form

    def _construct_form(self, i, **kwargs):
        kwargs['item'] = self.instance
        return super()._construct_form(i, **kwargs)


class VariationsField(forms.ModelMultipleChoiceField):

    def __init__(self, item=None, **kwargs):
        self.item = item
        super().__init__(self, **kwargs)

    def _get_choices(self):
        if not hasattr(self, 'item'):
            return ()
        print(self.item.pk)
        return ()

    choices = property(_get_choices, forms.ChoiceField._set_choices)
