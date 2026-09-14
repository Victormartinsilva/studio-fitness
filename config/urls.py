from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("contas/", include("apps.contas.urls")),
    path("cadastros/", include("apps.cadastros.urls")),
    path("planos/", include("apps.planos.urls")),
    path("financeiro/", include("apps.financeiro.urls")),
    path("agenda/", include("apps.agenda.urls")),
    path("avaliacoes/", include("apps.avaliacoes.urls")),
    path("modulos/", include("apps.modulos.urls")),
    path("assistente/", include("apps.assistente.urls")),
    path("", include("apps.painel.urls")),
]
