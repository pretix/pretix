from django.template.defaultfilters import date as _date
from django.utils.translation import get_language, ugettext_lazy as _


def daterange(df, dt):
    lng = get_language()

    if lng.startswith("de"):
        if df.year == dt.year and df.month == dt.month and df.day == dt.day:
            return "{}".format(_date(df, "j. F Y"))
        elif df.year == dt.year and df.month == dt.month:
            return "{}.–{}".format(_date(df, "j"), _date(dt, "j. F Y"))
        elif df.year == dt.year:
            return "{} – {}".format(_date(df, "j. F"), _date(dt, "j. F Y"))
    elif lng.startswith("en"):
        if df.year == dt.year and df.month == dt.month and df.day == dt.day:
            return "{}".format(_date(df, "N jS, Y"))
        elif df.year == dt.year and df.month == dt.month:
            return "{} – {}".format(_date(df, "N jS"), _date(dt, "jS, Y"))
        elif df.year == dt.year:
            return "{} – {}".format(_date(df, "N jS"), _date(dt, "N jS, Y"))

    return _("{date_from} – {date_to}").format(
        date_from=_date(df, "DATE_FORMAT"), date_to=_date(dt, "DATE_FORMAT")
    )
