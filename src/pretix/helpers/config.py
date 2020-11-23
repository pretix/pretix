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
