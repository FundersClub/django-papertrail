from django.conf.urls import url
from django.contrib import admin

admin.autodiscover()

app_name = 'tests'
urlpatterns = [
    url(r'^admin/', admin.site.urls),
]
