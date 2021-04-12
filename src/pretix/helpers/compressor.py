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
import shlex

from compressor.exceptions import FilterError
from compressor.filters import CompilerFilter
from django.conf import settings


class VueCompiler(CompilerFilter):
    # Based on work (c) Laura Klünder in https://github.com/codingcatgirl/django-vue-rollup
    # Released under Apache License 2.0

    def __init__(self, content, attrs, **kwargs):
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'npm_dir')
        node_path = os.path.join(settings.STATIC_ROOT, 'node_prefix', 'node_modules')
        self.rollup_bin = os.path.join(node_path, 'rollup', 'dist', 'bin', 'rollup')
        rollup_config = os.path.join(config_dir, 'rollup.config.js')
        if not os.path.exists(self.rollup_bin) and not settings.DEBUG:
            raise FilterError("Rollup not installed or pretix not built properly, please run 'make npminstall' in source root.")
        command = (
            ' '.join((
                'NODE_PATH=' + shlex.quote(node_path),
                shlex.quote(self.rollup_bin),
                '-c',
                shlex.quote(rollup_config))
            ) +
            ' --input {infile} -n {export_name} --file {outfile}'
        )
        super().__init__(content, command=command, **kwargs)

    def input(self, **kwargs):
        if self.filename is None:
            raise FilterError('VueCompiler can only compile files, not inline code.')
        if not os.path.exists(self.rollup_bin):
            raise FilterError("Rollup not installed, please run 'make npminstall' in source root.")
        self.options += (('export_name', re.sub(
            r'^([a-z])|[^a-z0-9A-Z]+([a-zA-Z0-9])?',
            lambda s: s.group(0)[-1].upper(),
            os.path.basename(self.filename).split('.')[0]
        )),)
        return super().input(**kwargs)
