from django.contrib import admin

from papertrail.admin import AdminEventLoggerMixin
from .models import Simple


@admin.register(Simple)
class SimpleAdmin(AdminEventLoggerMixin, admin.ModelAdmin):
    list_per_page = 5
