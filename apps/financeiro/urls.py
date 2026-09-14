from django.urls import path

from . import views

app_name = "financeiro"

urlpatterns = [
    path("cobrancas/", views.cobrancas, name="cobrancas"),
    path("cobrancas/<int:pk>/", views.cobrancas, name="cobrancas_editar"),
    path("cobrancas/gerar/", views.gerar, name="gerar"),
]
