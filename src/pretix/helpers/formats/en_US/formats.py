# Date according to https://docs.djangoproject.com/en/dev/ref/templates/builtins/#date
SHORT_DATE_FORMAT = 'm/d/Y'
SHORT_DATETIME_FORMAT = 'm/d/Y P'
TIME_FORMAT = 'P'
WEEK_FORMAT = '\\W W, o'
WEEK_DAY_FORMAT = 'D, M jS'

DATE_INPUT_FORMATS = [
    '%m/%d/%Y',
    '%Y-%m-%d',
    '%m/%d/%y',
]
TIME_INPUT_FORMATS = [
    '%I:%M %p',
    '%H:%M:%S',  # '14:30:59'
    '%H:%M:%S.%f',  # '14:30:59.000200'
    '%H:%M',  # '14:30'
]
