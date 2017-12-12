from enchant.tokenize import Filter

class CheckinFilter(Filter):
    """ If a word looks like checkin_count, it refers to a so-called variable in
    the code, and is treated as being spelled right."""

    def _skip(self, word):
        if word[:8] == "checkin_":
            return True
