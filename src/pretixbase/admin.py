from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import ugettext as _
from django import forms

from pretixbase.models import (
    User, Organizer, OrganizerPermission, Event, EventPermission,
    Property, PropertyValue, Item, ItemVariation, ItemCategory
)


class TixlUserCreationForm(forms.ModelForm):

    """
    A form that creates a user, with no privileges, from the given username and
    password.
    """
    error_messages = {
        'password_mismatch': _("The two password fields didn't match."),
    }
    password1 = forms.CharField(label=_("Password"),
                                widget=forms.PasswordInput)
    password2 = forms.CharField(label=_("Password confirmation"),
                                widget=forms.PasswordInput,
                                help_text=_("Enter the same password as above, for verification."))

    class Meta:
        model = User
        fields = ("email", "username", "event")

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError(
                self.error_messages['password_mismatch'],
                code='password_mismatch',
            )
        return password2

    def save(self, commit=True):
        user = super(TixlUserCreationForm, self).save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class TixlUserAdmin(UserAdmin):

    fieldsets = (
        (None, {'fields': ('identifier', 'event', 'username', 'password')}),
        (_('Personal info'), {'fields': ('familyname', 'givenname', 'email')}),
        (_('Locale'), {'fields': ('locale', 'timezone')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff',
                                       'groups', 'user_permissions')}),
    )
    list_display = ('identifier', 'event', 'username', 'email', 'givenname', 'familyname', 'is_staff')
    search_fields = ('identifier', 'username', 'givenname', 'familyname', 'email')
    ordering = ('identifier',)
    list_filter = ('is_staff', 'is_active', 'groups')
    add_form = TixlUserCreationForm


class OrganizerPermissionInline(admin.TabularInline):

    model = OrganizerPermission
    extra = 2


class OrganizerAdmin(admin.ModelAdmin):

    model = Organizer
    inlines = [OrganizerPermissionInline]
    list_display = ('name', 'slug')
    search_fields = ('name', 'slug')


class EventPermissionInline(admin.TabularInline):

    model = EventPermission
    extra = 2


class EventAdmin(admin.ModelAdmin):

    model = Event
    inlines = [EventPermissionInline]
    list_display = ('name', 'slug', 'organizer', 'date_from')
    search_fields = ('name', 'slug')
    list_filter = ('date_from', 'locale', 'currency')


class PropertyValueInline(admin.StackedInline):

    model = PropertyValue
    extra = 4


class PropertyAdmin(admin.ModelAdmin):

    model = Property
    inlines = [PropertyValueInline]
    list_display = ('name', 'event')
    search_fields = ('name', 'event')


class ItemCategoryAdmin(admin.ModelAdmin):

    model = ItemCategory
    list_display = ('name', 'event')
    search_fields = ('name', 'event')


class ItemVariationInline(admin.TabularInline):

    model = ItemVariation
    extra = 4


class ItemAdmin(admin.ModelAdmin):

    model = Item
    inlines = [ItemVariationInline]
    list_display = ('name', 'event', 'category')
    search_fields = ('name', 'event', 'category', 'short_description')


admin.site.register(User, TixlUserAdmin)
admin.site.register(Organizer, OrganizerAdmin)
admin.site.register(Event, EventAdmin)
admin.site.register(Property, PropertyAdmin)
admin.site.register(Item, ItemAdmin)
admin.site.register(ItemCategory, ItemCategoryAdmin)
