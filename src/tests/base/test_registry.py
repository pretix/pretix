#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
from unittest import mock

import pytest
from django.apps import apps

from pretix.base.logentrytypes import (
    ItemLogEntryType, LogEntryType, LogEntryTypeRegistry,
)
from pretix.base.models import Event
from pretix.base.signals import Registry


def test_registry_classes():
    animal_type_registry = Registry({"type": lambda s: s.__name__, "classis": lambda s: s.classis})

    @animal_type_registry.register
    class Cat:
        classis = 'mammalia'

        def make_sound(self):
            return "meow"

    @animal_type_registry.register
    class Dog:
        classis = 'mammalia'

        def make_sound(self):
            return "woof"

    @animal_type_registry.register
    class Cricket:
        classis = 'insecta'

        def make_sound(self):
            return "chirp"

    # test retrieving and instantiating a class based on metadata value
    clz, meta = animal_type_registry.get(type="Cat")
    assert clz().make_sound() == "meow"
    assert meta.get('type') == "Cat"

    clz, meta = animal_type_registry.get(type="Dog")
    assert clz().make_sound() == "woof"
    assert meta.get('type') == "Dog"

    # check that None is returned when no class exists with the specified metadata value
    clz, meta = animal_type_registry.get(type="Unicorn")
    assert clz is None
    assert meta is None

    # check that an error is raised when trying to retrieve by an undefined metadata key
    with pytest.raises(Exception):
        _, _ = animal_type_registry.get(whatever="hello")

    # test finding all entries with a given metadata value
    mammals = animal_type_registry.filter(classis='mammalia')
    assert set(cls for cls, meta in mammals) == {Cat, Dog}
    assert all(meta['classis'] == 'mammalia' for cls, meta in mammals)

    insects = animal_type_registry.filter(classis='insecta')
    assert set(cls for cls, meta in insects) == {Cricket}

    fantasy = animal_type_registry.filter(classis='fantasia')
    assert set(cls for cls, meta in fantasy) == set()

    # check normal object instantiation still works with our decorator
    assert Cat().make_sound() == "meow"


def test_registry_instances():
    animal_sound_registry = Registry({"animal": lambda s: s.animal})

    @animal_sound_registry.new("dog", "woof")
    @animal_sound_registry.new("cricket", "chirp")
    class AnimalSound:
        def __init__(self, animal, sound):
            self.animal = animal
            self.sound = sound

        def make_sound(self):
            return self.sound

    @animal_sound_registry.new()
    class CatSound(AnimalSound):
        def __init__(self):
            super().__init__(animal="cat", sound=["meow", "meww", "miaou"])
            self.i = 0

        def make_sound(self):
            self.i += 1
            return self.sound[self.i % len(self.sound)]

    # test registry
    assert animal_sound_registry.get(animal='dog')[0].make_sound() == "woof"
    assert animal_sound_registry.get(animal='dog')[0].make_sound() == "woof"
    assert animal_sound_registry.get(animal='cricket')[0].make_sound() == "chirp"
    assert animal_sound_registry.get(animal='cat')[0].make_sound() == "meww"
    assert animal_sound_registry.get(animal='cat')[0].make_sound() == "miaou"
    assert animal_sound_registry.get(animal='cat')[0].make_sound() == "meow"

    # check normal object instantiation still works with our decorator
    assert AnimalSound("test", "test").make_sound() == "test"


def test_registry_prevent_duplicates():
    my_registry = Registry({"animal": lambda s: s.animal})

    class AnimalSound:
        def __init__(self, animal, sound):
            self.animal = animal
            self.sound = sound

    cat = AnimalSound("cat", "meow")
    my_registry.register(cat)

    with pytest.raises(RuntimeError):
        my_registry.register(cat)


def test_logentrytype_registry():
    reg = LogEntryTypeRegistry()

    with mock.patch('pretix.base.signals.get_defining_app') as mock_get_defining_app:
        mock_get_defining_app.return_value = apps.get_app_config("testdummy")

        @reg.new("foo.mytype")
        class MyType(LogEntryType):
            pass

    with mock.patch('pretix.base.signals.get_defining_app') as mock_get_defining_app:
        mock_get_defining_app.return_value = "CORE"

        @reg.new("foo.myothertype")
        class MyOtherType(LogEntryType):
            pass

    typ, meta = reg.get(action_type="foo.mytype")
    assert isinstance(typ, MyType)
    assert meta['action_type'] == "foo.mytype"
    assert meta['plugin'] == apps.get_app_config("testdummy")

    typ, meta = reg.get(action_type="foo.myothertype")
    assert isinstance(typ, MyOtherType)
    assert meta['action_type'] == "foo.myothertype"
    assert meta['plugin'] == "CORE"

    by_my_plugin = reg.filter(plugin=apps.get_app_config("testdummy"))
    assert set(type(typ) for typ, meta in by_my_plugin) == {MyType}

    by_active_plugin = reg.filter(active_in=Event(plugins=""))
    assert set(type(typ) for typ, meta in by_active_plugin) == {MyOtherType}

    by_active_plugin = reg.filter(active_in=Event(plugins="tests.testdummy"))
    assert set(type(typ) for typ, meta in by_active_plugin) == {MyType, MyOtherType}


def test_logentrytype_registry_validation():
    reg = LogEntryTypeRegistry()

    with pytest.raises(TypeError, match='Must not register base classes, only derived ones'):
        reg.register(LogEntryType("foo.mytype"))

    with pytest.raises(TypeError, match='Must not register base classes, only derived ones'):
        reg.new_from_dict({"foo.mytype": "My Log Entry"})(ItemLogEntryType)

    with pytest.raises(TypeError, match='Entries must be derived from LogEntryType'):
        @reg.new()
        class MyType:
            pass
