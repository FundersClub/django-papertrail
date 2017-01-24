from __future__ import print_function

import datetime
import json
import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils import timezone

from papertrail import signals
from papertrail.fields import JSONField

LOG = logging.getLogger(__name__)


def coerce_to_queryset(instance_or_queryset):
    if isinstance(instance_or_queryset, models.Model):
        instance = instance_or_queryset
        return instance.__class__.objects.filter(pk=instance.pk)
    else:
        return instance_or_queryset


def related_to_q(obj, relation_name=None):
    '''
    Create a Q object expressing an event relation with an optional name.
    This is useful as a building block for Entry.objects.related_to(), and
    can be used to provide better query control for more complex queries
    without the boilerplate of directly querying an Entry's related objects.

    Example 1: OR query

        Entry.objects.filter(related_to(user1) | related_to(user2)).distinct()

    Example 2: building block to Entry.objects.related_to()

        The following are equivalent:

        Entry.objects.related_to(user=user1, group=group1)
        Entry.objects.filter(related_to_q(user1, 'user'))
                     .filter(related_to_q(group1, 'group'))

    '''
    related_qs = coerce_to_queryset(obj)
    content_type = ContentType.objects.get_for_model(related_qs.model)
    filters = {
        'targets__related_content_type': content_type,
        'targets__related_id__in': related_qs,
    }
    if relation_name:
        filters.update({'targets__relation_name': relation_name})
    return models.Q(**filters)


class RelatedObjectsQuerySetMixin(object):
    def _get_object_ids_in_papertrail(self, qs, relation_name):
        '''
        A helper method that receives an arbitrary queryset `qs` and a relation name
        `relation_name` and returns a list of object ids that are part of that queryset
        and ARE referenced by the `self` entries queryset.
        relation_name needs to point to the same type of objects the queryset this method
        receives is pointing to.

        For example, if qs has User objects whose ids are 1, 2, 3 and `self` has only
        one papertrail entry and that entry has targets={'user': user2}, calling
        _get_object_ids_in_papertrail(qs, 'user') would return only the id of user 2
        (because user1 and user3 do not have papertrail entries pointing at them)
        '''
        # Filter ourselves to only entries relating to the queryset the user
        # is passing us
        entries_related_to_qs = self.related_to(**{relation_name: qs})

        # Get the RelatedObject model (this would typically be EntryRelatedObject)
        targets_model = self.model().targets_model

        # Query related objects to get IDs of related objects that satisfy the following conditions:
        related_entries = (
            targets_model.objects
            # 1) They point to entries that are related to the queryset we received
            .filter(**{targets_model.owner_field_name + '__in': entries_related_to_qs})
            # 2) Their relation_name matches the one the user is querying for
            .filter(relation_name=relation_name)
        )

        # Return
        return related_entries.values_list('related_id', flat=True)

    def objects_not_represented(self, qs, relation_name):
        return qs.exclude(id__in=self._get_object_ids_in_papertrail(qs, relation_name))

    def objects_represented(self, qs, relation_name):
        return qs.filter(id__in=self._get_object_ids_in_papertrail(qs, relation_name))

    def related_to(self, *relations, **named_relations):
        '''
        Filter entries based on objects they pertain to, either generically or
        by a specific relation type.  If multiple relations are specified, the
        filter combines them with AND semantics.

        Examples:

            Tracking a simple 'follow' event where one user follows another,
            which is logged as:

            > user1 = User.objects.get(...)
            > user2 = User.objects.get(...)
            > log('user-followed', 'User followed another user', targets={'follower': user1, 'following': user2})

            First, a simple query for all events for user1, regardless of
            the type of relationship:

            > Entry.objects.related_to(user1)

            Next, to query for events involving both user1 and user2.

            > Entry.objects.related_to(user1, user2)

            Finally, to query for specific relationships, such as user1
            following user2:

            > Entry.objects.related_to(follower=user1, following=user2)
        '''
        entry_qs = self
        all_relations = [(None, r) for r in relations] + list(named_relations.items())

        for name, relation in all_relations:
            entry_qs = entry_qs.filter(related_to_q(relation, name))

        return entry_qs.distinct()


class EntryQuerySet(models.query.QuerySet, RelatedObjectsQuerySetMixin):
    def all_types(self):
        return self.order_by('type').values_list('type', flat=True).distinct()


class ModelWithRelatedObjectsMixin(object):
    def get(self, target, default=None):
        try:
            return self[target]
        except KeyError:
            return default

    def set(self, target_name, val, replace=True):
        '''
        Sets the updated target value, optionally replacing the existing target
        by that name.  If `replace` is False, raises an error if the target
        already exists.  `val` is generally a Django model instance, but can
        also be a tuple of (content_type, id) to reference an object as the
        contenttypes app does (this also allows references to deleted objects).
        '''
        target = self.get(target_name)
        if target and not replace:
            raise ValueError('Target {} already exists for this event'.format(target_name))

        attributes = {
            self.targets_model.owner_field_name: self,
            'relation_name': target_name,
        }
        target = target or self.targets_model(**attributes)
        if type(val) == tuple:
            content_type, object_id = val
            target.related_content_type = content_type
            target.related_id = object_id
            target.save()
        elif val:
            target.related_object = val
            target.save()
        return target

    @property
    def targets_map(self):
        return dict((t.relation_name, t.related_object) for t in self.targets.all())

    def update(self, targets_map):
        for target, val in (targets_map or {}).items():
            self[target] = val

    def __getitem__(self, target_name):
        # Optimization, in case we pre-fetched targets
        if hasattr(self, '_prefetched_objects_cache') and 'targets' in self._prefetched_objects_cache:
            for target in self._prefetched_objects_cache['targets']:
                if target.relation_name == target_name:
                    return target.related_object
            raise KeyError

        try:
            target = self.targets.get(relation_name=target_name)
            return target.related_object
        except self.targets_model.DoesNotExist:
            raise KeyError

    def __setitem__(self, target, val):
        return self.set(target, val)

    def __contains__(self, target_name):
        return self.targets.filter(relation_name=target_name).exists()


class Entry(models.Model, ModelWithRelatedObjectsMixin):
    timestamp = models.DateTimeField(db_index=True)
    type = models.CharField(max_length=50, db_index=True)
    message = models.CharField(max_length=512)
    data = JSONField(null=True)

    # Field for storing a custom 'key' for looking up specific events from
    # external sources.  This can be used to quickly and precisely look up
    # events that you can derive natural keys for, but aren't easily queryable
    # using Entry's other fields.
    external_key = models.CharField(max_length=255, null=True, db_index=True)

    objects = EntryQuerySet.as_manager()

    def __unicode__(self):
        return u'{} - {}'.format(self.type, self.message)

    class Meta:
        ordering = ['-timestamp']
        get_latest_by = 'timestamp'
        verbose_name_plural = 'entries'

    @property
    def targets_model(self):
        return EntryRelatedObject


# If you want to subclass this, make sure that the foreign key
# related name is called targets

class RelatedObject(models.Model):
    relation_name = models.CharField(max_length=100, db_index=True)
    related_content_type = models.ForeignKey(ContentType)
    related_id = models.PositiveIntegerField(db_index=True)
    related_object = GenericForeignKey('related_content_type', 'related_id')

    class Meta:
        abstract = True

    @property
    def safe_related_object(self):
        try:
            return self.related_object
        # This will happen if the model class of this object is not available, for example if the app providing it has been removed from INSTALLED_APPS
        except AttributeError:
            return None


class EntryRelatedObject(RelatedObject):
    entry = models.ForeignKey('Entry', related_name='targets')
    owner_field_name = 'entry'


def replace_object_in_papertrail(old_obj, new_obj, entry_qs=None):
    entry_qs = entry_qs or Entry.objects.all()
    old_obj_type = ContentType.objects.get_for_model(old_obj.__class__)
    new_obj_type = ContentType.objects.get_for_model(new_obj.__class__)
    related_qs = (EntryRelatedObject.objects.filter(
        entry__in=entry_qs,
        related_content_type=old_obj_type,
        related_id=old_obj.pk
        ))
    related_qs.update(related_content_type=new_obj_type,
                      related_id=new_obj.pk)


def json_default(o):
    """
    A `default` method for allowing objects with dates/decimals to be encoded into JSON.
    Usage: json.dumps(obj, default=_json_default)
    """
    if hasattr(o, 'to_json'):
        return o.to_json()
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, datetime.datetime):
        if o.tzinfo:
            return o.strftime('%Y-%m-%dT%H:%M:%S%z')
        return o.strftime('%Y-%m-%dT%H:%M:%S')
    if isinstance(o, datetime.date):
        return o.strftime('%Y-%m-%d')
    if isinstance(o, datetime.time):
        if o.tzinfo:
            return o.strftime('%H:%M:%S%z')
        return o.strftime('%H:%M:%S')


def json_serializeable(obj):
    """
    Attempts to return a copy of `obj` that is JSON serializeable
    """
    return json.loads(json.dumps(obj, default=json_default))


def log(event_type, message, data=None, timestamp=None, targets=None, external_key=None, data_adapter=json_serializeable):
    data_adapter = data_adapter or (lambda obj: obj)
    try:
        timestamp = timestamp or timezone.now()
        with transaction.atomic():

            # Enforce uniqueness on event_type/external_id if an external id is
            # provided
            if external_key:
                entry, created = Entry.objects.get_or_create(
                    type=event_type,
                    external_key=external_key,
                    defaults={
                        'message': message,
                        'data': data,
                        'timestamp': timestamp,
                    }
                )
                if not created:
                    return
            else:
                entry = Entry.objects.create(
                        type=event_type,
                        message=message,
                        data=data_adapter(data),
                        timestamp=timestamp,
                    )

            entry.update(targets)
            if getattr(settings, 'PAPERTRAIL_SHOW', False):
                WARNING = u'\033[95m'
                ENDC = u'\033[0m'
                print(WARNING + u'papertrail ' + ENDC + event_type + u" " + message)
    except:
        raise
    else:
        signals.event_logged.send_robust(sender=entry)
        return entry


# Expose aliases for common filter functions
related_to = Entry.objects.related_to
objects_not_represented = Entry.objects.objects_not_represented
objects_represented = Entry.objects.objects_represented
filter = Entry.objects.filter
exclude = Entry.objects.exclude
all_types = Entry.objects.all_types
