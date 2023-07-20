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
import sys
from pathlib import Path

import setuptools


sys.path.append(str(Path.cwd() / 'src'))


def _CustomBuild(*args, **kwargs):
    from pretix._build import CustomBuild
    return CustomBuild(*args, **kwargs)


def _CustomBuildExt(*args, **kwargs):
    from pretix._build import CustomBuildExt
    return CustomBuildExt(*args, **kwargs)


cmdclass = {
    'build': _CustomBuild,
    'build_ext': _CustomBuildExt,
}

if __name__ == "__main__":
    setuptools.setup(
        cmdclass=cmdclass,
    )
