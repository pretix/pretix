import os
from shutil import rmtree

import polib
from enchant import DictWithPWL
from enchant.checker import SpellChecker
from enchant.tokenize import Filter, Chunker, HTMLChunker, URLFilter

# The languages dict maps the language of the po-file to the the dictionary
# language used by pyenchant and an adjective for nicer output
LANGUAGES = {
    "de": "de_DE",
    "en": "en_US",
}

# LOCALES_DIR is the directory that contains the po-files per language.
# It follows the structure <lang>/LC_MESSAGES/django{js}.po where <lang> is the
# language that is translated into.
LOCALES_DIR = os.path.abspath('../../pretix/locale')

# IGNORES_DIR is the directory containing the lists with words to be ignored by
# the spellchecker, since they are spelled correctly.  The wordlists only need
# to contain uncapitalized words, the corresponding capitalized words are
# automatically recognized.
IGNORES_DIR = os.getcwd()

# BUILD_DIR is the directory that the output-files should be written to.
BUILD_DIR = os.path.abspath('./_build')

# List of words used by the HyphenationFilter
EDGECASE_WORDS = ["add-ons", 'same-origin"-requests', 'MT940', 'MT940-Format',
    'pre-selected', 'pretix.eu', 'pretix.eu-Blog', 'pretix.eu-Server', '4th']

# List of phrases that might be used out of language
PHRASES = ["ticketing powered by", "powered by"]

class PhraseChunker(Chunker):
    """
    It may happen that certain phrases are used in a context that would mark
    them as being incorrectly spelled. We chunk everything but those phrases to
    ignore them.

    The algorithm find the first index at which a phrase starts. In the case of
    multiple phrases, that is the first occurrence of any phrase. It returns
    everything before that phrase and continues with the text after that
    phrase.
    """

    def next(self):
        text = self._text
        offset = self.offset

        if offset >= len(text):
            raise StopIteration

        haystack = text[offset:].tounicode()

        needle = None
        index = None
        for p in PHRASES:
            try:
               found = haystack.index(p)
            except ValueError:
                continue
            if index is None or found < index:
                index = found
                needle = p

        if index is None:
            self.set_offset(len(text))
            return (text[offset:], offset)

        self.set_offset(index + len(needle))
        return (text[offset:index], offset)

class EdgecaseFilter(Filter):
    """
    Some words might be special edgecase words that cannot really be
    spellchecked and whose addition to the wordlist doesn't make sense.
    Examples are hyphenated words, since the tokenization will split them
    apart, which it should do, but which will sometimes lead to incorrect
    spellchecks.  Therefore, these have to be skipped it manually beforehand.
    """

    def _skip(self, word):
        if word in EDGECASE_WORDS:
            return True
        elif word.lower() in EDGECASE_WORDS:
            return True

class HTMLFilter(Filter):
    """
    We don't want to check HTML entities.
    """

    def _skip(self, word):
        if "&lt" in word:
            return True


class PythonFormatFilter(Filter):
    """
    We need to filter the python-format-words such as %(redeemed)s so that they
    don't get spell-checked.
    """
    def _skip(self, word):
        if word[:2] == "%(":
            return True
        if "{" in word:
            return True
        if word[:2] == "#%":
            return True
        return False

CHUNKERS = [HTMLChunker, PhraseChunker]
FILTERS = [PythonFormatFilter, URLFilter, HTMLFilter, EdgecaseFilter]


class Check:
    """
    A Check represents a po-file and a corresponding spellchecker for the
    po-files language. It also handles the output-file and some metadata.

    :param popath: The path to the po-file
    :type popath: path
    :param po: The po-file itself
    :type po: pofile
    :param checker: The spellchecker corresponding to the po-file's language
    :type checker: SpellChecker
    :param output_file: The file to write the checks output to
    :type output_file: file
    """
    def __init__(self, path):
        self.popath = path
        self.po = polib.pofile(path)
        lang = self.po.metadata["Language"]
        checklang = LANGUAGES[lang]
        ignore = self.get_ignorefile(lang)
        check_dict = DictWithPWL(checklang, pwl=ignore)
        self.checker = SpellChecker(check_dict, chunkers=CHUNKERS, filters=FILTERS)
        self.set_output(lang, ("djangojs" in path))

    def set_output(self, lang, js):
        out_dir = os.path.join(BUILD_DIR, lang)
        os.makedirs(out_dir, exist_ok=True)
        name = "output_js.txt" if js else 'output.txt'
        self.output_file = open(os.path.join(out_dir, name), 'a')

    def get_ignorefile(self, lang):
        for f in os.listdir(IGNORES_DIR):
            if lang in f:
                return f  # as there should be only one language file

def errmsg(outputfile, path, linenum, word):
    print("ERROR: {}:{}: {}".format(path, linenum, word))
    outputfile.write("ERROR: {}:{}: {}\n".format(path, linenum, word))

try:
    print('Creating build directory at', BUILD_DIR)
    os.mkdir(BUILD_DIR)
except FileExistsError:
    print("File or directory", BUILD_DIR, "already exists, deleting")
    rmtree(BUILD_DIR)
    print('Recreating build directory')
    os.mkdir(BUILD_DIR)
    print('Build directory done')

# checks contains one Check-Object for every po-file
checks = []

for root, dirs, files in os.walk(LOCALES_DIR):
    for f in files:
        if f.endswith(".po"):
            checks.append(Check(os.path.join(root, f)))

en_dict = DictWithPWL("en_US", pwl='./ignore_en.txt')
en_ckr = SpellChecker(en_dict, chunkers=CHUNKERS, filters=FILTERS)
output_file = open(os.path.join(BUILD_DIR, 'en_output.txt'), 'w')

for c in checks:
    for entry in c.po:
        if entry.obsolete:
            continue

        en_ckr.set_text(entry.msgid)
        for err in en_ckr:
            path = os.path.relpath(c.popath, start=LOCALES_DIR)
            errmsg(output_file, path, entry.linenum, err.word)

        c.checker.set_text(entry.msgstr)
        for err in c.checker:
            path = os.path.relpath(c.popath, start=LOCALES_DIR)
            errmsg(c.output_file, path, entry.linenum, err.word)

print("Spell-checking done. You can find the outputs in", BUILD_DIR + "/<lang>/{js_}output")
# TODO: extend english wordlist
# TODO: extend german wordlist
# TODO: use python test library to make good tests

# For reference: How sphinxcontrib-spelling reports errors:
# INFO 2017-12-13 10:26:55,977 sphinx.application logging
# api/resources/orders.rst:112:checkins:["chickens", "checking", "check ins",
# "check-ins", "kitchens", "checkin"]
