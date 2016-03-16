.PHONY: flake8 test coverage

flake8:
	flake8 --max-line-length=160 papertrail tests

isort:
	isort -rc papertrail tests

isort_check_only:
	isort -rc -c -df papertrail tests

test:
	DJANGO_SETTINGS_MODULE=tests.settings \
		django-admin test tests papertrail

coverage:
	coverage erase
	DJANGO_SETTINGS_MODULE=tests.settings \
		coverage run --branch --source=papertrail `which django-admin` test tests
	coverage html
