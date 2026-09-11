from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from .catalogo import MODULOS, obter_modulo


@login_required
def indice(request):
    return render(
        request,
        "modulos/indice.html",
        {
            "modulos": MODULOS,
            "pode_ver_previa": request.user.is_superuser,
            "aba": "modulos",
        },
    )


@login_required
def detalhe(request, slug):
    modulo = obter_modulo(slug)
    if not modulo:
        raise Http404("Módulo não encontrado.")

    return render(
        request,
        "modulos/detalhe.html",
        {
            "modulo": modulo,
            "pode_ver_previa": request.user.is_superuser,
            "aba": "modulos",
        },
    )
