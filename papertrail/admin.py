import collections
import itertools
import json

from django.conf.urls import url
from django.contrib import admin
from django.core import serializers
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils.encoding import force_text
from django.utils.html import format_html
from django.utils.text import capfirst
from django.utils.translation import ugettext as _

import papertrail
from papertrail.models import Entry, EntryRelatedObject


def admin_reverse_for_model(model):
    return reverse('admin:{}_{}_change'.format(model._meta.app_label, model._meta.model_name), args=[model.id])


class AdminEventLoggerMixin(object):
    '''
    Mixin for ModelAdmin classes to log admin actions to the papertrail
    application as well as to Django's built-in admin logging.
    '''
    papertrail_object_template = None

    # A map of category -> events used by the papertrail viewer to render
    # display filters
    papertrail_type_filters = {}

    # Override this field to change the 'target' object used for retrieving and
    # displaying history.  It should be a double__underscore__delimited
    # property related to the primary model admin object.
    papertrail_field = None

    def _record_changes(self, obj, fields=None):
        '''
        Records the state of `obj` to a JSON-serializable object, optionally
        recording only values in a list of `fields`.  If `fields` is not
        specified, all fields will be recorded.
        '''
        rec = json.loads(serializers.serialize('json', [obj]))[0]
        if fields:
            rec['fields'] = {k: v for k, v in rec['fields'].items()
                             if k in fields}
        return rec

    def _resolve_pt_object(self, object):
        instance = object

        if self.papertrail_field:
            for field_name in self.papertrail_field.split('__'):
                instance = getattr(instance, field_name, None)
                if not instance:
                    return object

        return instance

    def log_addition(self, request, object, message=None):
        if message is not None:
            super(AdminEventLoggerMixin, self).log_addition(request, object, message)
            try:
                message = json.loads(message)
            except ValueError:
                pass
        else:
            super(AdminEventLoggerMixin, self).log_addition(request, object)

        fields = self._record_changes(object)['fields']
        return papertrail.log(
            'admin-edit',
            'Created object',
            data={
                'action': 'add',
                'fields': fields,
                'message': message,
            },
            targets={
               'acting_user': request.user,
               'instance': self._resolve_pt_object(object),
            },
        )

    def log_change(self, request, object, message):
        super(AdminEventLoggerMixin, self).log_change(request, object, message)

        # construct_change_message() creates a JSON message that we load and
        # store here. (In case we don't get JSON back for some reason, still
        # store the message)
        try:
            data = {'changes': json.loads(message), 'action': 'change'}
        except ValueError:
            data = {'message': message, 'action': 'change'}

        return papertrail.log(
            'admin-edit',
            'Updated object',
            data=data,
            targets={
                'acting_user': request.user,
                'instance': self._resolve_pt_object(object),
            },
        )

    def log_deletion(self, request, object, object_repr):
        super(AdminEventLoggerMixin, self).log_deletion(request, object, object_repr)

        fields = self._record_changes(object)['fields']
        return papertrail.log(
            'admin-edit',
            'Deleted object',
            data={
                'action': 'delete',
                'fields': fields,
            },
            targets={
                'acting_user': request.user,
                'instance': self._resolve_pt_object(object),
            },
        )

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name

        urlpatterns = [
            url(r'^(.+)/papertrail/', self.admin_site.admin_view(self.view_papertrail_item), name=u'{0}_{1}_papertrail'.format(*info)),
        ] + super(AdminEventLoggerMixin, self).get_urls()

        return urlpatterns

    def get_actions(self, request):
        actions = super(AdminEventLoggerMixin, self).get_actions(request)
        func, name, desc = self.get_action('view_papertrail')
        actions[name] = (func, name, desc)
        return actions

    def view_papertrail_item(self, request, object_id, extra_context=None):
        get_object_or_404(self.model, id=object_id)
        return self.view_papertrail(request, self.model.objects.filter(id=object_id))

    def view_papertrail(self, request, queryset, extra_context=None):
        '''
        Action for displaying the papertrail for one or more selected admin
        items.
        '''

        # Map to alternate queryset if specified
        if self.papertrail_field:
            queryset = self._map_to_related_queryset(queryset, self.papertrail_field)

        action_list = Entry.objects.related_to(queryset).select_related()
        opts = queryset.model._meta
        app_label = opts.app_label

        available_type_filters = collections.OrderedDict(self.papertrail_type_filters)
        if available_type_filters:
            available_type_filters['Other'] = ('__other', )
        selected_type_filters = request.POST.getlist('papertrail-selected-type-filters')
        selected_types = list(itertools.chain.from_iterable(available_type_filters.get(k, []) for k in selected_type_filters))
        if '__other' in selected_types:
            all_types = list(itertools.chain.from_iterable(available_type_filters.values()))
            action_list = action_list.filter(Q(type__in=selected_types) | ~Q(type__in=all_types))
        elif selected_types:
            action_list = action_list.filter(type__in=selected_types)

        if queryset.count() == 1:
            obj = queryset[0]
            title = _('Paper Trail: %s') % force_text(obj)
        else:
            obj = None
            title = _('Paper Trail: %s %s') % (queryset.count(), opts.verbose_name_plural)

        context = {
            'title': title,
            'action_list': action_list,
            'module_name': capfirst(force_text(opts.verbose_name_plural)),
            'app_label': app_label,
            'opts': opts,
            'object': obj,
            'available_type_filters': available_type_filters,
            'selected_type_filters': selected_type_filters,
            'selected_actions': request.POST.getlist('_selected_action'),
        }
        context.update(extra_context or {})

        return render(request, self.papertrail_object_template or [
            "admin/%s/%s/object_papertrail.html" % (app_label, opts.object_name.lower()),
            "admin/%s/object_papertrail.html" % app_label,
            "admin/object_papertrail.html"
        ], context)
    view_papertrail.short_description = 'View Paper Trail'

    def _map_to_related_queryset(self, queryset, field):
        '''
        Given a queryset and an double__underscore__delimited field relation,
        return a list of the objects that are the target of that relation for
        all objects in the queryset.
        '''
        model = queryset.model

        # The easy part is finding the pks of the related objects
        pks = queryset.values_list('{}__pk'.format(field), flat=True)

        # The hard part is traversing the relation string and finding out what
        # model we're actually looking for.
        segments = field.split('__')
        for segment in segments:
            field = getattr(model, segment).field
            try:
                model = field.related.parent_model
            except AttributeError:
                model = field.rel.model

        # Once we have both pieces, we can just query the model for the ids
        return model.objects.filter(pk__in=pks)

    def construct_change_message(self, request, form, formsets, add=False):
        '''
        Construct a detailed change message from a changed object, including
        related objects updated via subforms.  Returns a JSON string containing
        a structure detailing the fields changed and their updated values.
        '''
        def add_related_change(changes, obj, action='change', fields=None):
            rec = self._record_changes(obj, fields=fields)
            rec['action'] = action
            changes['related_changes'].append(rec)
            return rec

        changes = {
            'action': 'change',
            'fields': self._record_changes(form.instance, form.changed_data)['fields'],
            'related_changes': [],
        }

        for formset in (formsets or []):
            for obj in formset.new_objects:
                add_related_change(changes, obj, action='add')
            for obj, changed_fields in formset.changed_objects:
                add_related_change(changes, obj, action='change', fields=changed_fields)
            for obj in formset.deleted_objects:
                add_related_change(changes, obj, action='add')

        return json.dumps(changes)


class EntryRelatedObjectInline(admin.StackedInline):
    model = EntryRelatedObject
    extra = 0
    fields = ('relation_name', 'related_content_type', 'related_model', )
    readonly_fields = ('related_model', )

    def related_model(self, obj):
        related_obj = obj.related_object
        return format_html(
            u'<a href="{}">{}</a>',
            admin_reverse_for_model(related_obj),
            related_obj,
        )


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ('type', 'message', 'timestamp', )
    search_fields = ('type', )
    inlines = (EntryRelatedObjectInline, )
