all: localecompile staticfiles
production: localecompile staticfiles compress

localecompile:
	./manage.py compilemessages

localegen:
	./manage.py makemessages --all --ignore "pretix/helpers/*"
	./manage.py makemessages --all -d djangojs --ignore "pretix/helpers/*" --ignore "static/jsi18n/*"

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
