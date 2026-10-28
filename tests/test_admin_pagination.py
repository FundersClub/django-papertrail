from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import path, reverse

from papertrail import log
from papertrail.admin import AdminEventLoggerMixin
from papertrail.models import Entry


class GroupAdmin(AdminEventLoggerMixin, admin.ModelAdmin):
    list_per_page = 2
    papertrail_type_filters = {'Selected': ('selected',)}


site = admin.AdminSite(name='admin')
site.register(Group, GroupAdmin)
site.register(Entry)
urlpatterns = [path('admin/', site.urls)]


@override_settings(ROOT_URLCONF=__name__)
class PaginationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='admin', email='admin@example.test', password='test-only')
        self.client.force_login(self.user)
        self.first = Group.objects.create(name='first')
        self.second = Group.objects.create(name='second')
        self.unselected = Group.objects.create(name='unselected')
        for index in range(5):
            log('selected', 'selected {}'.format(index), targets={'group': self.first})
        log('other', 'other entry', targets={'group': self.first})
        log('selected', 'second group entry', targets={'group': self.second})
        log('selected', 'unselected group entry', targets={'group': self.unselected})

    def test_object_pagination_keeps_filter(self):
        url = reverse('admin:auth_group_papertrail', args=[self.first.pk])
        response = self.client.post(url, {'papertrail-selected-type-filters': ['Selected'], 'page': 2})
        self.assertEqual(response.status_code, 200)
        page = response.context['action_list']
        self.assertEqual(page.number, 2)
        self.assertEqual(page.paginator.count, 5)
        self.assertEqual(len(page), 2)
        self.assertTrue(all(entry.type == 'selected' for entry in page))
        self.assertContains(response, 'name="papertrail-selected-type-filters" value="Selected"')
        self.assertContains(response, 'name="page" value="3"')
        self.assertNotContains(response, 'href="?page=')

    def test_action_pagination_keeps_selected_objects(self):
        response = self.client.post(reverse('admin:auth_group_changelist'), {
            'action': 'view_papertrail', 'index': 0,
            '_selected_action': [self.first.pk, self.second.pk],
            'papertrail-selected-type-filters': ['Selected'], 'page': 2,
        })
        self.assertEqual(response.status_code, 200)
        page = response.context['action_list']
        self.assertEqual(page.number, 2)
        self.assertEqual(page.paginator.count, 6)
        self.assertEqual(response.context['selected_actions'], [str(self.first.pk), str(self.second.pk)])
        for pk in (self.first.pk, self.second.pk):
            self.assertContains(response, 'name="_selected_action" value="{}"'.format(pk))
        self.assertContains(response, 'name="action" value="view_papertrail"')

    def test_select_across_survives_pagination(self):
        response = self.client.post(reverse('admin:auth_group_changelist'), {
            'action': 'view_papertrail', 'index': 0, 'select_across': '1',
            '_selected_action': [self.first.pk], 'page': 2,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['action_list'].paginator.count, 8)
        self.assertContains(response, 'name="select_across" value="1"')

    def test_invalid_pages_are_handled(self):
        url = reverse('admin:auth_group_papertrail', args=[self.first.pk])
        for value, expected in [('bad', 1), ('999', 3), ('0', 3)]:
            with self.subTest(page=value):
                response = self.client.get(url, {'page': value})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['action_list'].number, expected)

    def test_empty_history_renders(self):
        empty = Group.objects.create(name='empty')
        response = self.client.get(reverse('admin:auth_group_papertrail', args=[empty.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['action_list'].paginator.count, 0)
        self.assertContains(response, "doesn't have any events")
