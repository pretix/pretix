import polib
import enchant as en
from enchant.checker import SpellChecker

# TODO: expand to all files
popath = '/home/koebi/github/pretix/src/pretix/locale/de/LC_MESSAGES/django.po'
ignore_en = '/home/koebi/github/pretix/src/tests/locale/ignore_en.txt'
ignore_de = '/home/koebi/github/pretix/src/tests/locale/ignore_de.txt'
po = polib.pofile(popath)

# TODO: recognize language automatically
lang = po.metadata["Language"]

en_dict = en.DictWithPWL("en_US", pwl=ignore_en)
de_dict = en.DictWithPWL("de", pwl = ignore_de)

en_ckr = SpellChecker(en_dict)
de_ckr = SpellChecker(de_dict)

for entry in po:
    if entry.obsolete:
        continue

    en_ckr.set_text(entry.msgid)
    for err in en_ckr:
        print("ERROR:", popath,":",entry.linenum,":", err.word)

    de_ckr.set_text(entry.msgstr)
    for err in de_ckr:
        continue
        print("ERROR:", err.word)

# TODO: set up html filter?
# TODO: output to file as well as printing

# For reference: How sphinxcontrib-spelling reports errors:
# INFO 2017-12-13 10:26:55,977 sphinx.application logging api/resources/orders.rst:112:checkins:["chickens", "checking", "check ins", "check-ins", "kitchens", "checkin"]

