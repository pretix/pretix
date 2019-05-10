import glob
import importlib
import os
from contextlib import suppress

import pytest
from django.conf import settings
from django.dispatch import Signal

from pretix.base.signals import DeprecatedSignal

here = os.path.dirname(__file__)
doc_dir = os.path.join(here, "../../../doc")

plugin_docs = ""
for f in glob.glob(os.path.join(doc_dir, "development/api/*.rst")):
    with open(f, "r") as doc_file:
        plugin_docs += doc_file.read()


@pytest.mark.parametrize("app", sorted(settings.CORE_MODULES))
def test_documentation_includes_signals(app):
    with suppress(ImportError):
        module = importlib.import_module(app + ".signals")
        missing = []
        for key in dir(module):
            attrib = getattr(module, key)
            if isinstance(attrib, Signal) and not isinstance(attrib, DeprecatedSignal):
                if key not in plugin_docs:
                    missing.append(key)

        assert not missing, "The following signals are undocumented: %r" % missing
