all: localecompile staticfiles
production: localecompile staticfiles compress

localecompile:
	./manage.py compilemessages

localegen:
	./manage.py makemessages --all

staticfiles:
	./manage.py collectstatic --noinput

compress:
	./manage.py compress

test:
	py.test tests

coverage:
	coverage run -m py.test
