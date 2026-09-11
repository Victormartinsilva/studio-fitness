from django.urls import path

from . import grade as grade_view
from . import views

app_name = "agenda"

urlpatterns = [
    path("", views.minhas_sessoes, name="minhas_sessoes"),
    path("grade/", grade_view.grade, name="grade"),
    path("agendar/", views.agendar, name="agendar"),
    path("<int:pk>/cancelar/", views.cancelar, name="cancelar"),
]
