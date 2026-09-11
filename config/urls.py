from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("contas/", include("apps.contas.urls")),
    path("agenda/", include("apps.agenda.urls")),
    path("", include("apps.painel.urls")),
]
