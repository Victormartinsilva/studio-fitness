from django.urls import path

from . import views

app_name = "agenda"

urlpatterns = [
    path("", views.minhas_sessoes, name="minhas_sessoes"),
]
