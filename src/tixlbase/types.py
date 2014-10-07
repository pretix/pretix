class VariationDict(dict):
    """
    A VariationDict object behaves exactle the same as the Python built-in
    ``dict`` does, but adds some special methods. It is used for the dicts
    returned by ``Item.get_all_variations()`` to avoid duplicate code in the
    code calling this method.
    """

    def relevant_items(self):
        """
        Iterate over all items with numeric keys.

        This is in use because the variation dictionaries use property ids
        as key and have some special keys like 'variation'.
        """
        for i in self.items():
            if type(i[0]) is int:
                yield i

    def relevant_values(self):
        """
        Iterate over all values with numeric keys.

        This is in use because the variation dictionaries use property ids
        as key and have some special keys like 'variation'.
        """
        for i in self.items():
            if type(i[0]) is int:
                yield i[1]

    def identify(self):
        """
        Build an identifier for this dict. This can be any string used to
        compare one VariationDict to others.

        In the current implementation, it is a string containing a list of
        the PropertyValue id's, sorted by the Property id's and is therefore
        unique among one item.
        """
        order_key = lambda i: i[0]
        return ",".join([
            str(v[1].pk) for v in sorted(self.relevant_items(), key=order_key)
        ])

    def __eq__(self, other):
        if type(other) is type(self):
            return self.identify() == other.identify()
        else:
            return super().__eq__(other)

    def ordered_values(self):
        """
        Returns a list of values ordered by their keys
        """
        return [
            i[1] for i
            in sorted(
                [it for it in self.relevant_items()],
                key=lambda i: i[0]
            )
        ]

    def copy(self):
        """
        Return a one-level deep copy of this object (create a new
        VariationDict but make a shallow copy of the dict inside it).
        """
        new = VariationDict()
        for k, v in self.items():
            new[k] = v
        return new
