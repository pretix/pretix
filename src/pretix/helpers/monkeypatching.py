from datetime import datetime


def monkeypatch_vobject_performance():
    """
    This works around a performance issue in the unmaintained vobject library which calls
    a very expensive function for every event in a calendar. Since the slow function is
    mostly used to compare timezones to UTC, not to arbitrary other timezones, we can
    add a few early-out optimizations.
    """

    from vobject import icalendar

    old_tzinfo_eq = icalendar.tzinfo_eq
    test_date = datetime(2000, 1, 1)

    def new_tzinfo_eq(tzinfo1, tzinfo2, *args, **kwargs):
        if tzinfo1 is None:
            return tzinfo2 is None
        if tzinfo2 is None:
            return tzinfo1 is None

        n1 = tzinfo1.tzname(test_date)
        n2 = tzinfo2.tzname(test_date)
        if n1 == "UTC" and n2 == "UTC":
            return True
        if n1 == "UTC" or n2 == "UTC":
            return False
        return old_tzinfo_eq(tzinfo1, tzinfo2, *args, **kwargs)

    icalendar.tzinfo_eq = new_tzinfo_eq


def monkeypatch_all_at_ready():
    monkeypatch_vobject_performance()
