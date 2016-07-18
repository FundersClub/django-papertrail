# Attempt to use the built-in PostgreSQL json field, but if that is not
# available try the 3rd party jsonfield one.
try:
    from django.contrib.postgres.fields import JSONField as BaseJSONField
except:
    from jsonfield.fields import JSONField as BaseJSONField


class JSONField(BaseJSONField):
    pass
