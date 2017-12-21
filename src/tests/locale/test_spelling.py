import polib
import enchant as ec
import os
from enchant.checker import SpellChecker
from enchant.tokenize import Filter, HTMLChunker

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

# locales is the directory containing the translations
# ignores is the directory containing the ignore-files
# These wordlists only need to contain uncapitalized words, the corresponding capitalized words are automatically recognized.
# TODO: make this more python-y
locales = '../../pretix/locale'
ignores = os.listdir(".")

class Check:
    def __init__(self, path):
        self.popath = path
        self.po = polib.pofile(path)
        lang = self.po.metadata["Language"]
        checklang = languages[lang]
        self.get_ignorefile(lang)
        check_dict = ec.DictWithPWL(checklang, pwl=self.ignore)
        self.checker = SpellChecker(check_dict, chunkers=[HTMLChunker], filters=[PythonFormatFilter])
        self.output = open('_build/' + lang + '_output.txt', 'w')

    def get_ignorefile(self, lang):
        for f in ignores:
            if "ignore" in f and lang in f:
                self.ignore = f

# checks contains tuples of po-files and corresponding checkers
checks = []

for root, dirs, files in os.walk(locales):
    for f in files:
        if f.endswith(".po"):
            checks.append(Check(os.path.join(root, f)))

en_dict = ec.DictWithPWL("en_US", pwl='./ignore_en.txt')
en_ckr = SpellChecker(en_dict, chunkers=[HTMLChunker], filters=[PythonFormatFilter])
output = open('_build/en_output.txt', 'w')

try:
    print('Creating build directory…')
    os.mkdir('_build')
except FileExistsError:
    print('Build directory already exists.')

for c in checks:
    for entry in c.po:
        if entry.obsolete:
            continue

        en_ckr.set_text(entry.msgid)
        for err in en_ckr:
            print("ERROR:", c.popath, ":", entry.linenum, ":", err.word)
            output.write("ERROR:" + c.popath + ":" + str(entry.linenum) + ":" + err.word + "\n")


        c.checker.set_text(entry.msgstr)
        for err in c.checker:
            print("ERROR:", c.popath, ":", entry.linenum, ":", err.word)
            c.output.write("ERROR:" + c.popath + ":" + str(entry.linenum) + ":" + err.word + "\n")

print("Spell-checking done. You can find the outputs in \"_build/<lang>_output\".")
# TODO: extend english wordlist
# TODO: extend german wordlist
# TODO: use python test library to make good tests

# For reference: How sphinxcontrib-spelling reports errors:
# INFO 2017-12-13 10:26:55,977 sphinx.application logging api/resources/orders.rst:112:checkins:["chickens", "checking", "check ins", "check-ins", "kitchens", "checkin"]
