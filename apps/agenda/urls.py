from django.urls import path

from . import calendario, views
from . import grade as grade_view

app_name = "agenda"

urlpatterns = [
    path("", views.minhas_sessoes, name="minhas_sessoes"),
    path("grade/", grade_view.grade, name="grade"),
    path("mes/", calendario.mes, name="mes"),
    path("ano/", calendario.ano, name="ano"),
    path("agendar/", views.agendar, name="agendar"),
    path("<int:pk>/cancelar/", views.cancelar, name="cancelar"),
    path("<int:pk>/status/", views.status, name="status"),
    path("<int:pk>/remarcar/", views.remarcar, name="remarcar"),
    path("<int:pk>/", views.detalhe, name="detalhe"),
]
