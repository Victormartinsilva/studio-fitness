from django.urls import path

from . import views

app_name = "cadastros"

urlpatterns = [
    path("alunos/", views.alunos, name="alunos"),
    path("alunos/<int:pk>/", views.alunos, name="alunos_editar"),
    path("meus-alunos/", views.meus_alunos, name="meus_alunos"),
    path("equipamentos/", views.equipamentos, name="equipamentos"),
    path("equipamentos/<int:pk>/", views.equipamentos, name="equipamentos_editar"),
    path("tipos-sessao/", views.tipos_sessao, name="tipos_sessao"),
    path("tipos-sessao/<int:pk>/", views.tipos_sessao, name="tipos_sessao_editar"),
]
