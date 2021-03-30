all: localecompile staticfiles
production: localecompile staticfiles compress
LNGS:=`find pretix/locale/ -mindepth 1 -maxdepth 1 -type d -printf "-l %f "`

localecompile:
	./manage.py compilemessages

localegen:
	./manage.py makemessages --keep-pot --ignore "pretix/helpers/*" --ignore "pretix/static/npm_dir/*" $(LNGS)
	./manage.py makemessages --keep-pot -d djangojs --ignore "pretix/static/npm_dir/*" --ignore "pretix/helpers/*" --ignore "pretix/static/jsi18n/*" --ignore "pretix/static/jsi18n/*" --ignore "pretix/static.dist/*" --ignore "data/*" --ignore "pretix/static/rrule/*" --ignore "build/*" $(LNGS)

staticfiles: jsi18n
	./manage.py collectstatic --noinput

compress: npminstall
	./manage.py compress

jsi18n: localecompile
	./manage.py compilejsi18n

test:
	py.test tests

coverage:
	coverage run -m py.test

npminstall:
	# keep this in sync with setup.py!
	mkdir -p pretix/static.dist/node_prefix/
	cp -r pretix/static/npm_dir/* pretix/static.dist/node_prefix/
	npm install --prefix=pretix/static.dist/node_prefix

