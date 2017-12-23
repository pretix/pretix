import polib
import enchant as ec
import os
from enchant.checker import SpellChecker
from enchant.tokenize import Filter, HTMLChunker
from shutil import rmtree

class PythonFormatFilter(Filter):
    def _skip(self, word):
        if word[:2] == "%(":
            return True
        if word[0] == "{":
            return True
        return False

# The languages dict maps the language of the po-file to the the dictionary language used by pyenchant
languages = {
        "de": "de_DE",
        "en": "en_US",
}

# These wordlists in the IGNORES_DIR only need to contain uncapitalized words,
# the corresponding capitalized words are automatically recognized.
LOCALES_DIR = os.path.abspath('../../pretix/locale')
IGNORES_DIR = os.getcwd()
BUILD_DIR = os.path.abspath('./_build')

try:
    print('Creating build directory at' + BUILD_DIR + '…')
    os.mkdir(BUILD_DIR)
except FileExistsError:
    print("File or directory" + BUILD_DIR + "already exists, deleting…")
    rmtree(BUILD_DIR)
    print('Recreating build directory')
    os.mkdir(BUILD_DIR)
    print('Build directory done')

class Check:
    def __init__(self, path):
        self.popath = path
        self.po = polib.pofile(path)
        lang = self.po.metadata["Language"]
        checklang = languages[lang]
        self.get_ignorefile(lang)
        check_dict = ec.DictWithPWL(checklang, pwl=self.ignore)
        self.checker = SpellChecker(check_dict, chunkers=[HTMLChunker], filters=[PythonFormatFilter])
        self.set_output(lang)
        
    def set_output(self, lang):
        name = (lang + '_output.txt')
        files = os.listdir(BUILD_DIR)
        if name in files:
            self.output_file = open(os.path.join(BUILD_DIR, name), 'a')
        else:
            self.output_file = open(os.path.join(BUILD_DIR, name), 'w')

    def get_ignorefile(self, lang):
        for f in os.listdir(IGNORES_DIR):
            if lang in f:
                self.ignore = f
                return


# checks contains tuples of po-files and corresponding checkers
checks = []

for root, dirs, files in os.walk(LOCALES_DIR):
    for f in files:
        if f.endswith(".po"):
            checks.append(Check(os.path.join(root, f)))

en_dict = ec.DictWithPWL("en_US", pwl='./ignore_en.txt')
en_ckr = SpellChecker(en_dict, chunkers=[HTMLChunker], filters=[PythonFormatFilter])
output_file = open('_build/en_output.txt', 'w')

for c in checks:
    for entry in c.po:
        if entry.obsolete: continue

        en_ckr.set_text(entry.msgid)
        for err in en_ckr:
            path = os.path.relpath(c.popath, start=LOCALES_DIR)
            print("ERROR: {}:{}: {}".format(path, entry.linenum, err.word))
            output_file.write("ERROR: {}:{}: {}\n".format(path, entry.linenum, err.word))

        c.checker.set_text(entry.msgstr)
        for err in c.checker:
            path = os.path.relpath(c.popath, start=LOCALES_DIR)
            print("ERROR: {}:{}: {}".format(path, entry.linenum, err.word))
            c.output_file.write("ERROR: {}:{}: {}\n".format(path, entry.linenum, err.word))

print("Spell-checking done. You can find the outputs in '_build/<lang>_output'.")
# TODO: extend english wordlist
# TODO: extend german wordlist
# TODO: use python test library to make good tests

# For reference: How sphinxcontrib-spelling reports errors:
# INFO 2017-12-13 10:26:55,977 sphinx.application logging api/resources/orders.rst:112:checkins:["chickens", "checking", "check ins", "check-ins", "kitchens", "checkin"]
