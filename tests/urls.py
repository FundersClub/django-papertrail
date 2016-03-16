from django.conf.urls import include, url
from django.contrib import admin

admin.autodiscover()

app_name = 'tests'
urlpatterns = [
    url(r'^admin/', include(admin.site.urls)),
]
