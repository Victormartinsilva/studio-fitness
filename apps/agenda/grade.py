"""
Grade diária da agenda: uma coluna por equipamento, blocos posicionados em pixels.

Mantém a mesma leitura do motor: cada sessão vira três blocos visuais —
preparo (reserva_inicio → inicio), sessão (inicio → fim) e troca (fim → reserva_fim).
"""
from datetime import date, datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.cadastros.models import Equipamento

from .models import BloqueioEquipamento, Sessao

HORA_INICIO = 7          # primeira hora exibida
HORA_FIM = 21            # última hora exibida (exclusiva)
ALTURA_HORA = 72         # px por hora
PX_POR_MIN = ALTURA_HORA / 60


def _offset(momento, dia):
    """Posição em px de um datetime dentro da pista do dia."""
    local = timezone.localtime(momento)
    if local.date() < dia:
        minutos = 0
    elif local.date() > dia:
        minutos = (HORA_FIM - HORA_INICIO) * 60
    else:
        minutos = (local.hour - HORA_INICIO) * 60 + local.minute
    limite = (HORA_FIM - HORA_INICIO) * 60
    return max(0, min(minutos, limite)) * PX_POR_MIN


def _bloco(classe, inicio, fim, dia, titulo="", subtitulo=""):
    top = _offset(inicio, dia)
    altura = max(6, _offset(fim, dia) - top)
    return {
        "classe": classe,
        "top": round(top, 1),
        "altura": round(altura, 1),
        "titulo": titulo,
        "subtitulo": subtitulo,
    }


@login_required
def grade(request):
    hoje = timezone.localdate()
    try:
        dia = date.fromisoformat(request.GET.get("data", ""))
    except ValueError:
        dia = hoje

    inicio_dia = timezone.make_aware(datetime.combine(dia, time(HORA_INICIO, 0)))
    fim_dia = timezone.make_aware(datetime.combine(dia, time(0, 0)) + timedelta(hours=HORA_FIM))

    sessoes = (
        Sessao.objects.exclude(status=Sessao.Status.CANCELADA)
        .filter(reserva_inicio__lt=fim_dia, reserva_fim__gt=inicio_dia)
        .select_related("aluno", "professor__usuario", "tipo", "equipamento")
    )
    bloqueios = BloqueioEquipamento.objects.filter(inicio__lt=fim_dia, fim__gt=inicio_dia)

    equipamentos = Equipamento.objects.exclude(status=Equipamento.Status.INATIVO)

    colunas = []
    for equipamento in equipamentos:
        blocos = []
        for sessao in sessoes:
            if sessao.equipamento_id != equipamento.id:
                continue
            if sessao.reserva_inicio < sessao.inicio:
                blocos.append(_bloco("preparo", sessao.reserva_inicio, sessao.inicio, dia))
            if sessao.reserva_fim > sessao.fim:
                blocos.append(_bloco("troca", sessao.fim, sessao.reserva_fim, dia))
            blocos.append(
                _bloco(
                    "sessao",
                    sessao.inicio,
                    sessao.fim,
                    dia,
                    titulo="{:%H:%M} – {:%H:%M} · {}".format(
                        timezone.localtime(sessao.inicio), timezone.localtime(sessao.fim), sessao.aluno
                    ),
                    subtitulo="{} · {}".format(sessao.professor, sessao.tipo),
                )
            )
        for bloqueio in bloqueios:
            if bloqueio.equipamento_id != equipamento.id:
                continue
            blocos.append(
                _bloco(
                    "bloqueio",
                    bloqueio.inicio,
                    bloqueio.fim,
                    dia,
                    titulo=bloqueio.descricao or bloqueio.get_motivo_display(),
                    subtitulo="{:%H:%M} – {:%H:%M}".format(
                        timezone.localtime(bloqueio.inicio), timezone.localtime(bloqueio.fim)
                    ),
                )
            )
        colunas.append({"equipamento": equipamento, "blocos": blocos})

    minutos_reservados = sum(
        (s.reserva_fim - s.reserva_inicio).total_seconds() / 60
        for s in sessoes
        if s.equipamento_id
    )
    capacidade = max(1, len(colunas)) * (HORA_FIM - HORA_INICIO) * 60
    segunda = dia - timedelta(days=dia.weekday())

    return render(
        request,
        "agenda/grade.html",
        {
            "aba": "agenda",
            "data": dia,
            "hoje": hoje,
            "dia_anterior": dia - timedelta(days=1),
            "dia_seguinte": dia + timedelta(days=1),
            "semana": [
                {"data": segunda + timedelta(days=i), "selecionado": segunda + timedelta(days=i) == dia}
                for i in range(6)
            ],
            "horas": ["{:02d}:00".format(h) for h in range(HORA_INICIO, HORA_FIM)],
            "altura_hora": ALTURA_HORA,
            "altura_hora_menos1": ALTURA_HORA - 1,
            "altura_pista": (HORA_FIM - HORA_INICIO) * ALTURA_HORA,
            "colunas": colunas,
            "total_sessoes": len([s for s in sessoes]),
            "ocupacao": round(minutos_reservados / capacidade * 100),
            "pode_agendar": request.user.is_superuser or request.user.is_gestor or request.user.is_professor,
        },
    )
