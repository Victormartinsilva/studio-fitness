from django.urls import path

from . import views

app_name = "planos"

urlpatterns = [
    path("planos/", views.planos, name="planos"),
    path("planos/<int:pk>/", views.planos, name="planos_editar"),
    path("contratacoes/", views.contratacoes, name="contratacoes"),
    path("contratacoes/<int:pk>/", views.contratacoes, name="contratacoes_editar"),
]
