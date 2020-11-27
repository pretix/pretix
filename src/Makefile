all: localecompile staticfiles
production: localecompile staticfiles compress
LNGS:=`find pretix/locale/ -mindepth 1 -maxdepth 1 -type d -printf "-l %f "`

localecompile:
	./manage.py compilemessages

localegen:
	./manage.py makemessages --keep-pot --ignore "pretix/helpers/*" $(LNGS)
	./manage.py makemessages --keep-pot -d djangojs --ignore "pretix/helpers/*" --ignore "pretix/static/jsi18n/*" --ignore "pretix/static/jsi18n/*" --ignore "pretix/static.dist/*" --ignore "data/*" --ignore "pretix/static/rrule/*" --ignore "build/*" $(LNGS)

staticfiles: jsi18n
	./manage.py collectstatic --noinput

compress:
	./manage.py compress

jsi18n: localecompile
	./manage.py compilejsi18n

test:
	py.test tests

coverage:
	coverage run -m py.test
