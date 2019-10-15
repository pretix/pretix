"""
Django, for theoretically very valid reasons, creates migrations for *every single thing*
we change on a model. Even the `help_text`! This makes sense, as we don't know if any
database backend unknown to us might actually use this information for its database schema.

However, pretix only supports PostgreSQL, MySQL, MariaDB and SQLite and we can be pretty
certain that some changes to models will never require a change to the database. In this case,
not creating a migration for certain changes will save us some performance while applying them
*and* allow for a cleaner git history. Win-win!

Only caveat is that we need to do some dirty monkeypatching to achieve it...
"""
from django.core.management.commands.makemigrations import Command as Parent
from django.db import models
from django.db.migrations.operations import models as modelops
from django_countries.fields import CountryField

modelops.AlterModelOptions.ALTER_OPTION_KEYS.remove("verbose_name")
modelops.AlterModelOptions.ALTER_OPTION_KEYS.remove("verbose_name_plural")
modelops.AlterModelOptions.ALTER_OPTION_KEYS.remove("ordering")
modelops.AlterModelOptions.ALTER_OPTION_KEYS.remove("get_latest_by")
modelops.AlterModelOptions.ALTER_OPTION_KEYS.remove("default_manager_name")
modelops.AlterModelOptions.ALTER_OPTION_KEYS.remove("permissions")
modelops.AlterModelOptions.ALTER_OPTION_KEYS.remove("default_permissions")
IGNORED_ATTRS = [
    # (field type, attribute name, banlist of field sub-types)
    (models.Field, 'verbose_name', []),
    (models.Field, 'help_text', []),
    (models.Field, 'validators', []),
    (models.Field, 'editable', [models.DateField, models.DateTimeField, models.DateField, models.BinaryField]),
    (models.Field, 'blank', [models.DateField, models.DateTimeField, models.AutoField, models.NullBooleanField,
                             models.TimeField]),
    (models.CharField, 'choices', [CountryField])
]

original_deconstruct = models.Field.deconstruct


def new_deconstruct(self):
    name, path, args, kwargs = original_deconstruct(self)
    for ftype, attr, banlist in IGNORED_ATTRS:
        if isinstance(self, ftype) and not any(isinstance(self, ft) for ft in banlist):
            kwargs.pop(attr, None)
    return name, path, args, kwargs


models.Field.deconstruct = new_deconstruct


class Command(Parent):
    pass
