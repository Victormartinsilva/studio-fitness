from django.urls import path

from . import views

app_name = "avaliacoes"

urlpatterns = [
    path("aluno/<int:aluno_pk>/", views.evolucao, name="evolucao"),
    path("aluno/<int:aluno_pk>/<int:pk>/", views.evolucao, name="editar"),
]
