import datetime
import sys


def date_fromisocalendar(isoyear, isoweek, isoday):
    if sys.version_info < (3, 8):
        return datetime.datetime.strptime(f'{isoyear}-W{isoweek}-{isoday}', "%G-W%V-%u")
    else:
        return datetime.datetime.fromisocalendar(isoyear, isoweek, isoday)
