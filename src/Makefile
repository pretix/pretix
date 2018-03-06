all: localecompile staticfiles
production: localecompile staticfiles compress

localecompile:
	./manage.py compilemessages

localegen:
	./manage.py makemessages --keep-pot --all --ignore "pretix/helpers/*"
	./manage.py makemessages --keep-pot --all -d djangojs --ignore "pretix/helpers/*" --ignore "pretix/static/jsi18n/*" --ignore "pretix/static/jsi18n/*" --ignore "pretix/static.dist/*" --ignore "data/*" --ignore "build/*"

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
