from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

from apps.contas.permissions import admin_required

from .catalogo import EIXOS, MODULOS, obter_modulo
from .models import PAPEL_CONFIGURAVEL_CHOICES, PAPEL_EIXO_CHOICES, VisibilidadeEixo, VisibilidadeModulo


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
    """Permite ao administrador decidir, por perfil: (1) quais módulos em
    desenvolvimento aparecem como prévia ("em breve") no painel do usuário,
    e (2) quais eixos reais da navegação (Meus alunos, Alunos, Equipamentos,
    Tipos de sessão, Planos) aparecem no menu de cada perfil."""
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
        # Só mexe nos eixos se a tabela de "Seções da navegação" foi de fato
        # enviada nesse POST (marcador oculto abaixo). Isso evita que um POST
        # parcial (ex.: só a tabela de módulos) apague/oculte todos os eixos.
        if "eixos_enviados" in request.POST:
            for papel, _ in PAPEL_EIXO_CHOICES:
                for eixo in EIXOS:
                    if papel not in eixo.papeis_padrao:
                        continue
                    campo = f"eixo__{papel}__{eixo.slug}"
                    VisibilidadeEixo.objects.update_or_create(
                        papel=papel,
                        slug=eixo.slug,
                        defaults={"visivel": campo in request.POST},
                    )
        messages.success(request, "Visibilidade dos módulos e eixos atualizada.")
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

    ocultos_por_papel = {
        papel: set(VisibilidadeEixo.objects.filter(papel=papel, visivel=False).values_list("slug", flat=True))
        for papel, _ in PAPEL_EIXO_CHOICES
    }
    linhas_eixos = [
        {
            "eixo": eixo,
            "papeis": [
                {
                    "papel": papel,
                    "rotulo": rotulo,
                    "aplicavel": papel in eixo.papeis_padrao,
                    "marcado": papel in eixo.papeis_padrao and eixo.slug not in ocultos_por_papel[papel],
                }
                for papel, rotulo in PAPEL_EIXO_CHOICES
            ],
        }
        for eixo in EIXOS
    ]

    return render(
        request,
        "modulos/visoes.html",
        {
            "linhas": linhas,
            "papeis_modulos": PAPEL_CONFIGURAVEL_CHOICES,
            "linhas_eixos": linhas_eixos,
            "papeis_eixos": PAPEL_EIXO_CHOICES,
            "aba": "modulos",
        },
    )
