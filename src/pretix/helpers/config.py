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
import os
import re
from configparser import _UNSET


class EnvOrParserConfig:
    def __init__(self, configparser):
        self.cp = configparser

    def _envkey(self, section, option):
        section = re.sub('[^a-zA-Z0-9]', '_', section.upper())
        option = re.sub('[^a-zA-Z0-9]', '_', option.upper())
        return f'PRETIX_{section}_{option}'

    def get(self, section, option, *, raw=False, vars=None, fallback=_UNSET):
        if self._envkey(section, option) in os.environ:
            return os.environ[self._envkey(section, option)]
        return self.cp.get(section, option, raw=raw, vars=vars, fallback=fallback)

    def getint(self, section, option, *, raw=False, vars=None, fallback=_UNSET):
        if self._envkey(section, option) in os.environ:
            return int(os.environ[self._envkey(section, option)])
        return self.cp.getint(section, option, raw=raw, vars=vars, fallback=fallback)

    def getfloat(self, section, option, *, raw=False, vars=None, fallback=_UNSET):
        if self._envkey(section, option) in os.environ:
            return float(os.environ[self._envkey(section, option)])
        return self.cp.getfloat(section, option, raw=raw, vars=vars, fallback=fallback)

    def getboolean(self, section, option, *, raw=False, vars=None, fallback=_UNSET):
        if self._envkey(section, option) in os.environ:
            return self.cp._convert_to_boolean(os.environ[self._envkey(section, option)])
        return self.cp.getboolean(section, option, raw=raw, vars=vars, fallback=fallback)

    def has_section(self, section):
        if any(k.startswith(self._envkey(section, '')) for k in os.environ):
            return True
        return self.cp.has_section(section)

    def has_option(self, section, option):
        if self._envkey(section, option) in os.environ:
            return True
        return self.cp.has_option(section, option)
