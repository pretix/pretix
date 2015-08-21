import importlib.util
import sys


def module_exists(modname):
    if sys.version_info[0:1] >= (3, 4):
        return bool(importlib.util.find_spec(modname))
    else:
        return bool(importlib.find_loader(modname))
