from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.cadastros.models import Aluno, Equipamento
from apps.agenda import motor
from apps.agenda.models import Sessao
from apps.modulos.catalogo import MODULOS
from apps.modulos.models import VisibilidadeModulo

from .alertas import gerar_alertas


@login_required
def home(request):
    usuario = request.user
    agora = timezone.now()
    hoje = timezone.localdate()

    sessoes = Sessao.objects.exclude(status=Sessao.Status.CANCELADA).select_related(
        "aluno", "professor__usuario", "tipo", "equipamento"
    )
    if usuario.is_professor and hasattr(usuario, "professor"):
        minhas = sessoes.filter(professor=usuario.professor)
    elif usuario.is_aluno and hasattr(usuario, "aluno"):
        minhas = sessoes.filter(aluno=usuario.aluno)
    else:
        minhas = sessoes

    proxima = minhas.filter(inicio__gte=agora).order_by("inicio").first()

    kpis = []
    if usuario.is_superuser or usuario.is_gestor:
        resumo = motor.resumo_do_dia(hoje)
        # `total_sessoes` do resumo inclui canceladas (documentado em
        # `motor.resumo_do_dia`) — descontamos para manter o mesmo
        # significado que "Sessões hoje" sempre teve aqui (só as ativas).
        sessoes_ativas_hoje = resumo["total_sessoes"] - resumo["por_status"].get(Sessao.Status.CANCELADA, 0)
        equipamentos = Equipamento.objects.filter(status=Equipamento.Status.ATIVO).count()
        kpis = [
            {"valor": "{}%".format(resumo["ocupacao_pct"]), "nome": "Ocupação hoje"},
            {"valor": sessoes_ativas_hoje, "nome": "Sessões hoje"},
            {"valor": Aluno.objects.filter(ativo=True).count(), "nome": "Alunos ativos"},
            {"valor": equipamentos, "nome": "Equipamentos ativos"},
        ]

    modulos_previa = []
    if not (usuario.is_superuser or usuario.is_gestor):
        slugs_visiveis = set(
            VisibilidadeModulo.objects.filter(papel=usuario.papel, visivel=True).values_list("slug", flat=True)
        )
        modulos_previa = [modulo for modulo in MODULOS if not modulo.liberado and modulo.slug in slugs_visiveis]

    return render(
        request,
        "painel/home.html",
        {
            "aba": "inicio",
            "hoje": hoje,
            "alertas": gerar_alertas(usuario),
            "proxima": proxima,
            "kpis": kpis,
            "pode_agendar": usuario.is_superuser or usuario.is_gestor or usuario.is_professor,
            "proximas_24h": minhas.filter(inicio__gte=agora, inicio__lte=agora + timedelta(hours=24)).count(),
            "modulos_previa": modulos_previa,
        },
    )

