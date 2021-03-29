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
        node_path = os.path.join(settings.STATIC_ROOT, 'node_prefix', 'node_modules', 'pretix', 'node_modules')
        rollup_bin = os.path.join(node_path, 'rollup', 'dist', 'bin', 'rollup')
        rollup_config = os.path.join(config_dir, 'rollup.config.js')
        command = (
            ' '.join((
                'NODE_PATH=' + shlex.quote(node_path),
                shlex.quote(rollup_bin),
                '-c',
                shlex.quote(rollup_config))
            ) +
            ' --input {infile} -n {export_name} --file {outfile}'
        )
        super().__init__(content, command=command, **kwargs)

    def input(self, **kwargs):
        if self.filename is None:
            raise FilterError('VueCompiler can only compile files, not inline code.')
        self.options += (('export_name', re.sub(
            r'^([a-z])|[^a-z0-9A-Z]+([a-zA-Z0-9])?',
            lambda s: s.group(0)[-1].upper(),
            os.path.basename(self.filename).split('.')[0]
        )),)
        return super().input(**kwargs)
