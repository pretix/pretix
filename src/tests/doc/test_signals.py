#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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
