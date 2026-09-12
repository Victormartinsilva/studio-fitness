from django.urls import path

from . import views

app_name = "assistente"

urlpatterns = [
    path("mensagem", views.mensagem, name="mensagem"),
    path("confirmar", views.confirmar, name="confirmar"),
]
