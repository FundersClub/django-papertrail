Version 1.1.0 - HAS BREAKING CHANGES
===========================================================
*   Switched to testing with PostgreSQL
*   Switch to using native JSONField on Django>=1.9. If you
    are upgrading an existing installation you will need to
    execute the following SQL command manually:
        `ALTER TABLE "papertrail_entry" ALTER COLUMN "data" TYPE jsonb USING "data"::jsonb;`
    This is because there is no easy way to change the
    underlying field AND dropping the dependency on django-jsonfield
    at the same time. Sorry :(


Version 1.0.5 (2016-06-22)
===========================================================

*   Started tracking changes.
