from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.cadastros.models import Aluno, Equipamento
from apps.agenda.models import Sessao

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
        do_dia = sessoes.filter(inicio__date=hoje)
        minutos = sum((s.reserva_fim - s.reserva_inicio).total_seconds() / 60 for s in do_dia if s.equipamento_id)
        equipamentos = Equipamento.objects.filter(status=Equipamento.Status.ATIVO).count()
        capacidade = max(1, equipamentos) * 14 * 60  # 07:00–21:00
        kpis = [
            {"valor": "{}%".format(round(minutos / capacidade * 100)), "nome": "Ocupação hoje"},
            {"valor": do_dia.count(), "nome": "Sessões hoje"},
            {"valor": Aluno.objects.filter(ativo=True).count(), "nome": "Alunos ativos"},
            {"valor": equipamentos, "nome": "Equipamentos ativos"},
        ]

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
        },
    )
