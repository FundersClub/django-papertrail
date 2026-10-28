import unittest

from django import VERSION as django_version
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.dispatch import receiver
from django.db import connection
from django.db.models.signals import post_save
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from papertrail import log, signals
from papertrail.models import Entry, EntryRelatedObject, related_to_q, replace_object_in_papertrail

User = get_user_model()


class TestBasic(TestCase):

    def test_entry_logging(self):

        log('test', 'Testing entry')

        user = User.objects.create_user('testuser', 'test@example.com')
        log('test-user-created', 'User created', targets={'user': user})

        group = Group.objects.create(name='Test Group')
        log('test-group-created', 'Group created', targets={'group': group})

        group.user_set.add(user)
        log('test-group-added-user', 'User added to group', targets={'user': user, 'group': group})

        log('test-extra-data', 'Testing extra data', data={'key': 'value'})

        tznow = timezone.now()
        overridden_timestamp_entry = log(
            'test-overridden-timestamp',
            'Testing overriding a timestamp for operations like importing',
            timestamp=tznow,
        )
        self.assertEqual(tznow, overridden_timestamp_entry.timestamp)

        qs = Entry.objects.filter(type__startswith='test')
        self.assertEqual(qs.count(), 6)

        self.assertEqual(qs.related_to(user).count(), 2)
        self.assertEqual(qs.related_to(group).count(), 2)
        self.assertEqual(qs.related_to(user=user).count(), 2)
        self.assertEqual(qs.related_to(group=group).count(), 2)
        self.assertEqual(qs.related_to(user=group).count(), 0)
        self.assertEqual(qs.related_to(group=user).count(), 0)
        self.assertEqual(qs.related_to(user, group).count(), 1)
        self.assertEqual(qs.related_to(user=user, group=group).count(), 1)

        # test chaining and equivalence
        self.assertEqual(set(qs.related_to(user=user)
                               .related_to(group=group)
                               .values_list('id', flat=True)),
                         set(qs.related_to(user=user, group=group)
                               .values_list('id', flat=True)))

        # test related_to Q object
        self.assertEqual(set(qs.related_to(user, group)
                               .values_list('id', flat=True)),
                         set(qs.filter(related_to_q(user))
                               .filter(related_to_q(group))
                               .values_list('id', flat=True)))

        self.assertEqual(qs.filter(related_to_q(user) | related_to_q(group))
                           .distinct().count(),
                         3)

    def test_signals(self):
        event_logged_counter = [0]

        @receiver(signals.event_logged)
        def on_event_logged(sender, **kwargs):
            event_logged_counter[0] += 1

        log('test', 'Testing signal')
        self.assertEqual(event_logged_counter[0], 1)

    def test_setters_and_getters(self):
        e = log('test-entry', 'Test Entry')
        self.assertEqual(e.targets_map, {})

        user = User.objects.create_user('testuser', 'test@example.com')
        e.set('target1', user)

        # Basic lookup
        self.assertEqual(e.get('target1'), user)
        self.assertEqual(e['target1'], user)

        # Invalid key lookup and getting a default for non-existent targets
        with self.assertRaises(KeyError):
            e['target2']
        self.assertEqual(e.get('target2'), None)
        self.assertEqual(e.get('target2', 'a-default-value'), 'a-default-value')

        # Contains ('in') implementation
        self.assertTrue('target1' in e)
        self.assertFalse('target2' in e)

        # Setting and retrieving a 'virtual' target
        user_type = ContentType.objects.get_for_model(User)
        e.set('virtual', (user_type, 10000))
        self.assertEqual(e['virtual'], None)
        self.assertEqual(e.get('virtual', 'a-default-value'), None)

    def test_change_related_object(self):
        user1 = User.objects.create_user('testuser1', 'test1@example.com')
        user2 = User.objects.create_user('testuser2', 'test2@example.com')

        Entry.objects.all().delete()

        log('test-entry', 'This is a test entry', targets={'user': user1})
        log('test-entry', 'This is a test entry', targets={'user': user2})

        qs = Entry.objects.all()
        self.assertEqual(qs.related_to(user1).count(), 1)
        self.assertEqual(qs.related_to(user2).count(), 1)

        replace_object_in_papertrail(user1, user2)

        qs = Entry.objects.all()
        self.assertEqual(qs.related_to(user1).count(), 0)
        self.assertEqual(qs.related_to(user2).count(), 2)

    def test_objects_represented(self):
        user1 = User.objects.create_user('testuser1', 'test1@example.com')
        user2 = User.objects.create_user('testuser2', 'test2@example.com')
        user3 = User.objects.create_user('testuser3', 'test3@example.com')
        some_group = Group.objects.create(name='some group')
        some_group2 = Group.objects.create(name='some group 2')
        some_group3 = Group.objects.create(name='some group 3')

        log('test-entry', 'Test 1', targets={'user': user1, 'group': some_group})
        log('test-entry', 'Test 2', targets={'user': user2, 'group': some_group})
        log('test-entry', 'Test 3', targets={'user': user2, 'group': some_group2})
        log('test-entry', 'Test 4', targets={'blah': user1, 'group': some_group3})

        all_users = User.objects.all()
        self.assertEqual(
            set(Entry.objects.filter(type='test-entry').objects_represented(all_users, 'user')),
            set([user1, user2])
        )
        self.assertEqual(
            set(Entry.objects.filter(type='test-entry').related_to(group=some_group).objects_represented(all_users, 'user')),
            set([user1, user2]),
        )
        self.assertEqual(
            Entry.objects.filter(type='test-entry').related_to(group=some_group2).objects_represented(all_users, 'user').get(),
            user2,
        )
        self.assertTrue(
            Entry.objects.filter(type='test-entry').related_to(group=some_group3).exists(),
        )
        self.assertFalse(
            Entry.objects.filter(type='test-entry').related_to(group=some_group3).objects_represented(all_users, 'user').exists(),
        )
        self.assertEqual(
            Entry.objects.filter(type='test-entry').objects_not_represented(all_users, 'user').get(),
            user3
        )

    @unittest.skipIf(django_version < (1, 9), 'no native JSONField')
    def test_json_field_filtering(self):
        log('test', 'test', data={
            'field': 'value',
        })

        self.assertTrue(
            Entry.objects.filter(data__field='value').exists()
        )


class TestNewEntryTargets(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('audit-user', 'audit@example.com')
        self.group = Group.objects.create(name='Audit group')
        self.user_type = ContentType.objects.get_for_model(User)
        ContentType.objects.get_for_model(Group)

    def test_new_targets_have_no_related_record_selects(self):
        with CaptureQueriesContext(connection) as queries:
            entry = log('new-targets', 'Three targets', targets={
                'user': self.user,
                'group': self.group,
                'deleted-user': (self.user_type, 1000000),
                'empty': None,
            })
        reads = [q['sql'] for q in queries if q['sql'].lstrip().startswith('SELECT')
                 and 'papertrail_entryrelatedobject' in q['sql']]
        self.assertEqual(reads, [])
        self.assertEqual(entry.targets.count(), 3)
        self.assertEqual(entry['user'], self.user)
        self.assertEqual(entry['group'], self.group)
        self.assertIsNone(entry['deleted-user'])
        self.assertNotIn('empty', entry)
        self.assertEqual(entry.targets.get(relation_name='deleted-user').related_id, 1000000)

    def test_target_save_and_event_signals_see_saved_relations(self):
        saved = []
        logged = []

        def target_saved(sender, instance, created, **kwargs):
            saved.append((instance.relation_name, created))

        def event_logged(sender, **kwargs):
            logged.append(sender.targets_map)

        post_save.connect(target_saved, sender=EntryRelatedObject)
        signals.event_logged.connect(event_logged)
        try:
            log('new-target-signals', 'Two targets', targets={'user': self.user, 'group': self.group})
        finally:
            post_save.disconnect(target_saved, sender=EntryRelatedObject)
            signals.event_logged.disconnect(event_logged)
        self.assertEqual(saved, [('user', True), ('group', True)])
        self.assertEqual(logged, [{'user': self.user, 'group': self.group}])

    def test_invalid_target_rolls_back_entry_and_earlier_relations(self):
        previous_target_count = EntryRelatedObject.objects.count()
        with self.assertRaises(ValueError):
            log('invalid-target', 'Must roll back', targets={
                'user': self.user, 'unsaved': Group(name='Not saved'),
            })
        self.assertFalse(Entry.objects.filter(type='invalid-target').exists())
        self.assertEqual(EntryRelatedObject.objects.count(), previous_target_count)

    def test_external_key_does_not_add_targets_to_existing_entry(self):
        entry = log('external-target', 'Original', targets={'user': self.user}, external_key='same')
        result = log('external-target', 'Repeated', targets={'group': self.group}, external_key='same')
        self.assertIsNone(result)
        self.assertEqual(Entry.objects.filter(type='external-target').count(), 1)
        self.assertEqual(entry.targets_map, {'user': self.user})

    def test_entry_save_hooks_keep_existing_target_lookup_path(self):
        def entry_saved(sender, instance, created, **kwargs):
            if created:
                instance.set('hook', self.group)

        post_save.connect(entry_saved, sender=Entry)
        try:
            with CaptureQueriesContext(connection) as queries:
                entry = log('entry-hook', 'Hook and input targets', targets={'user': self.user})
        finally:
            post_save.disconnect(entry_saved, sender=Entry)
        self.assertEqual(entry.targets_map, {'hook': self.group, 'user': self.user})
        self.assertTrue(any(q['sql'].lstrip().startswith('SELECT')
                            and 'papertrail_entryrelatedobject' in q['sql'] for q in queries))
