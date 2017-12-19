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

locales = os.path.dirname(__file__) + '../../pretix/locale'
for root, dirs, files in os.walk(locales):
    for f in files:
        if f.endswith(".po"):
            print(os.path.join(root, f))

quit()
# TODO: expand to all files
# idee: dict mit mapping von po.metadata["Language"] -> Language Code, den wir
# an ec.DictWithPWL geben können, und mit dem die entsprechende ignore-file
# bezeichnet wird
# Dann können wir alle .po-files in "pretix/locale" finden, hauen die in eine Datenstruktur, die jeder po-file einen checker zuordnet, und lassen einen check laufen


popath = '/home/koebi/github/pretix/src/pretix/locale/de/LC_MESSAGES/django.po'
ignore_en = '/home/koebi/github/pretix/src/tests/locale/ignore_en.txt'
ignore_de = '/home/koebi/github/pretix/src/tests/locale/ignore_de.txt'
po = polib.pofile(popath)

# TODO: recognize language automatically
lang = po.metadata["Language"]

# The wordlists only need to contain uncapitalized words, the corresponding
# capitalized words are automatically recognized.
en_dict = ec.DictWithPWL("en_US", pwl=ignore_en)
de_dict = ec.DictWithPWL("de", pwl = ignore_de)

en_ckr = SpellChecker(en_dict, chunkers=[HTMLChunker], filters=[PythonFormatFilter])
de_ckr = SpellChecker(de_dict, chunkers=[HTMLChunker], filters=[PythonFormatFilter])

try:
    print('Creating build directory…')
    os.mkdir('_build')
except FileExistsError:
    print('Build directory already exists.')

of_en = open('_build/en_output.txt', 'w')
of_de = open('_build/de_output.txt', 'w')

flags = []

for entry in po:
    if entry.obsolete:
        continue

    en_ckr.set_text(entry.msgid)
    for err in en_ckr:
        print("ERROR:", popath, ":", entry.linenum, ":", err.word)
        of_en.write("ERROR:" + popath + ":" + str(entry.linenum) + ":" + err.word + "\n")


    de_ckr.set_text(entry.msgstr)
    for err in de_ckr:
        print("ERROR:", popath, ":", entry.linenum, ":", err.word)
        of_de.write("ERROR:" + popath + ":" + str(entry.linenum) + ":" + err.word + "\n")

print("Spell-checking done. You can find the outputs in", of_en.name, "and", of_de.name, ".")
# TODO: extend english wordlist
# TODO: extend german wordlist
# TODO: use python test library to make good tests

# For reference: How sphinxcontrib-spelling reports errors:
# INFO 2017-12-13 10:26:55,977 sphinx.application logging api/resources/orders.rst:112:checkins:["chickens", "checking", "check ins", "check-ins", "kitchens", "checkin"]

