from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .alertas import gerar_alertas


@login_required
def home(request):
    alertas = gerar_alertas(request.user)
    return render(request, "painel/home.html", {"alertas": alertas})
