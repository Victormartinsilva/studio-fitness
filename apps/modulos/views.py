from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

from apps.contas.permissions import admin_required

from .catalogo import MODULOS, obter_modulo
from .models import PAPEL_CONFIGURAVEL_CHOICES, VisibilidadeModulo


@admin_required
def indice(request):
    return render(
        request,
        "modulos/indice.html",
        {
            "modulos": MODULOS,
            "aba": "modulos",
        },
    )


@admin_required
def detalhe(request, slug):
    modulo = obter_modulo(slug)
    if not modulo:
        raise Http404("Módulo não encontrado.")

    return render(
        request,
        "modulos/detalhe.html",
        {
            "modulo": modulo,
            "aba": "modulos",
        },
    )


@admin_required
def visoes(request):
    """Permite ao administrador decidir, por perfil, quais módulos em
    desenvolvimento aparecem como prévia ("em breve") no painel do usuário."""
    modulos_configuraveis = [modulo for modulo in MODULOS if not modulo.liberado]

    if request.method == "POST":
        for papel, _ in PAPEL_CONFIGURAVEL_CHOICES:
            for modulo in modulos_configuraveis:
                campo = f"{papel}__{modulo.slug}"
                VisibilidadeModulo.objects.update_or_create(
                    papel=papel,
                    slug=modulo.slug,
                    defaults={"visivel": campo in request.POST},
                )
        messages.success(request, "Visibilidade dos módulos atualizada.")
        return redirect("modulos:visoes")

    visiveis = set(
        VisibilidadeModulo.objects.filter(visivel=True).values_list("papel", "slug")
    )
    linhas = [
        {
            "modulo": modulo,
            "papeis": [
                {"papel": papel, "rotulo": rotulo, "marcado": (papel, modulo.slug) in visiveis}
                for papel, rotulo in PAPEL_CONFIGURAVEL_CHOICES
            ],
        }
        for modulo in modulos_configuraveis
    ]

    return render(
        request,
        "modulos/visoes.html",
        {
            "linhas": linhas,
            "aba": "modulos",
        },
    )
