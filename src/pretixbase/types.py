class VariationDict(dict):
    """
    A VariationDict object behaves exactle the same as the Python built-in
    ``dict`` does, but adds some special methods. It is used for the dicts
    returned by ``Item.get_all_variations()`` to avoid duplicate code in the
    code calling this method.
    """
    IGNORE_KEYS = ('variation', 'key', 'available', 'price')

    def relevant_items(self) -> "list[(str, PropertyValue)]":
        """
        Iterate over all items with numeric keys.

        This is in use because the variation dictionaries use property ids
        as key and have some special keys like 'variation'.
        """
        return (i for i in self.items() if i[0] not in self.IGNORE_KEYS)

    def relevant_values(self) -> "list[PropertyValue]":
        """
        Iterate over all values with numeric keys.

        This is in use because the variation dictionaries use property ids
        as key and have some special keys like 'variation'.
        """
        return (i[1] for i in self.items() if i[0] not in self.IGNORE_KEYS)

    def identify(self) -> str:
        """
        Build a simple and unique identifier for this dict. This can be any string
        used to compare one VariationDict to others.

        In the current implementation, it is a string containing a list of
        the PropertyValue id's, sorted by the Property id's and is therefore
        unique among one item.
        """
        def order_key(i):
            return i[0]
        return ",".join((
            str(v[1].pk) for v in sorted(self.relevant_items(), key=order_key)
        ))

    def key(self) -> str:
        """
        Build an identifier for this dict which exactly specifies the combination
        for this variation without any doubt. This can be used to "talk" about a
        variation in network communication.

        In the current implementation, it is a string containing a list of
        the propertyid:valueid tuples without any specific order and is therefore
        not useful to compare two VariationDicts for equality.
        """
        return ",".join((
            str(v[0]) + ":" + str(v[1].pk) for v in self.relevant_items()
        ))

    def __eq__(self, other):
        if type(other) is type(self):
            return self.identify() == other.identify()
        else:
            return super().__eq__(other)

    def empty(self):
        """
        Returns true, if this VariationDict does not contain any "real" data like
        references to PropertyValues, but only "metadata".
        """
        return not next(self.relevant_items(), False)

    def ordered_values(self) -> "list[ItemVariation]":
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

    def __str__(self):
        return " – ".join([v.value for v in self.ordered_values()])

    def copy(self) -> "VariationDict":
        """
        Return a one-level deep copy of this object (create a new
        VariationDict but make a shallow copy of the dict inside it).
        """
        new = VariationDict()
        for k, v in self.items():
            new[k] = v
        return new
