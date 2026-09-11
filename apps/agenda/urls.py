from django.urls import path

from . import views

app_name = "agenda"

urlpatterns = [
    path("", views.minhas_sessoes, name="minhas_sessoes"),
    path("agendar/", views.agendar, name="agendar"),
    path("<int:pk>/cancelar/", views.cancelar, name="cancelar"),
]
