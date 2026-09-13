from django.urls import path

from . import views

app_name = "avaliacoes"

urlpatterns = [
    path("minha-evolucao/", views.minha_evolucao, name="minha_evolucao"),
    path("minha-evolucao/comparar/", views.comparar, name="minha_comparacao"),
    path("aluno/<int:aluno_pk>/", views.evolucao, name="evolucao"),
    path("aluno/<int:aluno_pk>/comparar/", views.comparar, name="comparar"),
    path("aluno/<int:aluno_pk>/<int:pk>/", views.evolucao, name="editar"),
]
