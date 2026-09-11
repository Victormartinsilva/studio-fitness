from django.urls import path

from . import views

app_name = "modulos"

urlpatterns = [
    path("", views.indice, name="indice"),
    path("<slug:slug>/", views.detalhe, name="detalhe"),
]
