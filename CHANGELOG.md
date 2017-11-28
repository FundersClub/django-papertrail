Version 1.1.6
------------------------
*   Gracefully handle models not registered in admin when rendering papertrail entry admin pages.

Version 1.1.5
------------------------
*   Update the `message` field to be a TextField.

Version 1.1.4
------------------------
*   Django 1.10 and 1.11 support.


Version 1.1.3
------------------------
*   Make papertrail admin viewer resilient to the model class referenced
    by the related object not being available (this would happen, for example,
    when an app is removed from INSTALLED_APPS but it's Content Type object
    is still in the database).


Version 1.1.2
------------------------
*   Add default Entry admin


Version 1.1.1
------------------------
*   Add a new `data_adapter` argument to `papertrail.log`. The method
    pointed by this argument allows the caller to pass a function which
    transforms `data` before it is written to the database. It defaults
    to `papertrail.model.json_serializeable` which is a convenience method
    (albeit a tad slow) used to convert complex objects into JSON-serializeable
    representations. This includes dealing with datetime and Decimal fields
    which are not natively supported.
    This is a hack made necessary to allow easy logging of such data types
    as Django's built-in `JSONField` does not provide a way to customize
    the JSON serialization :(


Version 1.1.0 - HAS BREAKING CHANGES
------------------------
*   Switched to testing with PostgreSQL
*   Switch to using native JSONField on Django>=1.9. If you
    are upgrading an existing installation you will need to
    execute the following SQL command manually: `ALTER TABLE "papertrail_entry" ALTER COLUMN "data" TYPE jsonb USING "data"::jsonb;` This is because there is no easy way to change the underlying field AND dropping the dependency on django-jsonfield at the same time. Sorry :(


Version 1.0.5 (2016-06-22)
------------------------
*   Started tracking changes.
