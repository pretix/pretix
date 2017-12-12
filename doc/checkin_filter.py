from enchant.tokenize import get_tokenizer, Filter, unit_tokenize

class CheckinFilter(Filter):
    """ If a word looks like checkin_count, it refers to a so-called variable in
    the code, and is treated as being spelled right."""

    def _split(self, word):
        if word[:8] == "checkin_":
            return unit_tokenize(word[8:])

        return unit_tokenize(word)
