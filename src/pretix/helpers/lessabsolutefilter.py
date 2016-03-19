from compressor.filters.base import CompilerFilter
from compressor.filters.css_default import CssAbsoluteFilter

from pretix.settings import STATIC_ROOT, STATICFILES_DIRS


class LessFilter(CompilerFilter):
    def __init__(self, content, attrs, **kwargs):
        cmd = 'lessc --include-path=%s {infile} {outfile}' % ":".join(STATICFILES_DIRS + [STATIC_ROOT])
        super(LessFilter, self).__init__(content, command=cmd, **kwargs)

    def input(self, **kwargs):
        content = super(LessFilter, self).input(**kwargs)
        kwargs.setdefault('filename', self.filename)
        return CssAbsoluteFilter(content).input(**kwargs)
