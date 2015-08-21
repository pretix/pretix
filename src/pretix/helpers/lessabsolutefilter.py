from compressor.filters.base import CompilerFilter
from compressor.filters.css_default import CssAbsoluteFilter


class LessFilter(CompilerFilter):
    def __init__(self, content, attrs, **kwargs):
        super(LessFilter, self).__init__(content, command='lessc {infile} {outfile}', **kwargs)

    def input(self, **kwargs):
        content = super(LessFilter, self).input(**kwargs)
        kwargs.setdefault('filename', self.filename)
        return CssAbsoluteFilter(content).input(**kwargs)
