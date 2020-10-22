from datetime import date

from pretix.plugins.banktransfer.tasks import parse_date


def test_date_formats():
    dt = date(year=2020, month=7, day=1)
    assert dt == parse_date("01.07.2020")
    assert dt == parse_date("01.07.20")
    assert dt == parse_date("1.7.2020")
    assert dt == parse_date("1.7.20")

    assert dt == parse_date("07/01/2020")
    assert dt == parse_date("07/01/20")
    assert dt == parse_date("7/1/2020")
    assert dt == parse_date("7/1/20")

    assert dt == parse_date("2020/07/01")

    assert dt == parse_date("2020-07-01")
    assert dt == parse_date("2020-7-1")
