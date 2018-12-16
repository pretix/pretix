from datetime import date

from django.utils import translation

from pretix.helpers.daterange import daterange


def test_same_day_german():
    with translation.override('de'):
        df = date(2003, 2, 1)
        assert daterange(df, df) == "1. Februar 2003"


def test_same_day_english():
    with translation.override('en'):
        df = date(2003, 2, 1)
        assert daterange(df, df) == "Feb. 1st, 2003"


def test_same_day_spanish():
    with translation.override('es'):
        df = date(2003, 2, 1)
        assert daterange(df, df) == "1 de Febrero de 2003"


def test_same_month_german():
    with translation.override('de'):
        df = date(2003, 2, 1)
        dt = date(2003, 2, 3)
        assert daterange(df, dt) == "1.–3. Februar 2003"


def test_same_month_english():
    with translation.override('en'):
        df = date(2003, 2, 1)
        dt = date(2003, 2, 3)
        assert daterange(df, dt) == "Feb. 1st – 3rd, 2003"


def test_same_month_spanish():
    with translation.override('es'):
        df = date(2003, 2, 1)
        dt = date(2003, 2, 3)
        assert daterange(df, dt) == "1 - 3 de Febrero de 2003"


def test_same_year_german():
    with translation.override('de'):
        df = date(2003, 2, 1)
        dt = date(2003, 4, 3)
        assert daterange(df, dt) == "1. Februar – 3. April 2003"


def test_same_year_english():
    with translation.override('en'):
        df = date(2003, 2, 1)
        dt = date(2003, 4, 3)
        assert daterange(df, dt) == "Feb. 1st – April 3rd, 2003"


def test_same_year_spanish():
    with translation.override('es'):
        df = date(2003, 2, 1)
        dt = date(2003, 4, 3)
        assert daterange(df, dt) == "1 de Febrero - 3 de Abril de 2003"


def test_different_dates_german():
    with translation.override('de'):
        df = date(2003, 2, 1)
        dt = date(2005, 4, 3)
        assert daterange(df, dt) == "1. Februar 2003 – 3. April 2005"


def test_different_dates_english():
    with translation.override('en'):
        df = date(2003, 2, 1)
        dt = date(2005, 4, 3)
        assert daterange(df, dt) == "Feb. 1, 2003 – April 3, 2005"


def test_different_dates_spanish():
    with translation.override('es'):
        df = date(2003, 2, 1)
        dt = date(2005, 4, 3)
        assert daterange(df, dt) == "1 de Febrero de 2003 – 3 de Abril de 2005"
