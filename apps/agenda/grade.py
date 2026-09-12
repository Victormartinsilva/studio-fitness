"""
Grade diária da agenda: uma coluna por equipamento, blocos posicionados em pixels.

Mantém a mesma leitura do motor: cada sessão vira três blocos visuais —
preparo (reserva_inicio → inicio), sessão (inicio → fim) e troca (fim → reserva_fim).
"""
from datetime import date, datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from apps.cadastros.models import Equipamento

from .models import BloqueioEquipamento, Sessao

HORA_INICIO = 7          # primeira hora exibida
HORA_FIM = 21            # última hora exibida (exclusiva)
ALTURA_HORA = 72         # px por hora
PX_POR_MIN = ALTURA_HORA / 60
SLOT_MIN = 30            # granularidade dos horários livres clicáveis
SLOT_MIN_MINIMO = 15     # não mostra sobra de vaga menor que isso no fim de um intervalo


GAP_PX = 3               # espaço visual entre reservas distintas (evita blocos "colados")
DIAS_ANTES_NA_FAIXA = 7  # quantos dias antes do selecionado aparecem na faixa rolável
DIAS_DEPOIS_NA_FAIXA = 14  # quantos dias depois do selecionado aparecem na faixa rolável


def _minutos(momento, dia):
    """Minuto (clipado à janela do dia) de um datetime dentro da pista do dia."""
    local = timezone.localtime(momento)
    if local.date() < dia:
        minutos = 0
    elif local.date() > dia:
        minutos = (HORA_FIM - HORA_INICIO) * 60
    else:
        minutos = (local.hour - HORA_INICIO) * 60 + local.minute
    limite = (HORA_FIM - HORA_INICIO) * 60
    return max(0, min(minutos, limite))


def _offset(momento, dia):
    """Posição em px de um datetime dentro da pista do dia."""
    return _minutos(momento, dia) * PX_POR_MIN


def _bloco(classe, inicio, fim, dia, titulo="", subtitulo="", inset_topo=False, inset_base=False):
    top = _offset(inicio, dia)
    altura = _offset(fim, dia) - top
    if inset_topo:
        top += GAP_PX
        altura -= GAP_PX
    if inset_base:
        altura -= GAP_PX
    altura = max(6, altura)
    return {
        "classe": classe,
        # Formatado aqui (ponto decimal fixo) em vez de deixar o template
        # renderizar o float: com locale pt-br, "{{ valor }}" vira "831,6"
        # (vírgula), o que quebra o CSS inline "top:831,6px" e faz todo
        # bloco cair para top:0 (empilhado no topo da grade).
        "top": "{:.1f}".format(top),
        "altura": "{:.1f}".format(altura),
        "titulo": titulo,
        "subtitulo": subtitulo,
    }


def _vagas_livres(ocupados, dia, equipamento_id, agora):
    """Calcula os intervalos sem sessão/bloqueio na pista e devolve blocos
    clicáveis de SLOT_MIN minutos para permitir agendar direto na grade."""
    limite = (HORA_FIM - HORA_INICIO) * 60

    ocupados = sorted(ocupados)
    livres_min = []
    cursor = 0
    for inicio_min, fim_min in ocupados:
        inicio_min = max(0, min(inicio_min, limite))
        fim_min = max(0, min(fim_min, limite))
        if inicio_min > cursor:
            livres_min.append((cursor, inicio_min))
        cursor = max(cursor, fim_min)
    if cursor < limite:
        livres_min.append((cursor, limite))

    vagas = []
    for inicio_gap, fim_gap in livres_min:
        m = inicio_gap
        while m < fim_gap:
            fim_slot = min(m + SLOT_MIN, fim_gap)
            if fim_slot - m < SLOT_MIN_MINIMO:
                break
            hh, mm = divmod(HORA_INICIO * 60 + m, 60)
            momento = timezone.make_aware(datetime.combine(dia, time(hh, mm)))
            if momento >= agora:
                vagas.append(
                    {
                        "top": "{:.1f}".format(m * PX_POR_MIN),
                        "altura": "{:.1f}".format((fim_slot - m) * PX_POR_MIN),
                        "titulo": "{:02d}:{:02d}".format(hh, mm),
                        "href": "{}?data={}&hora_inicio={:02d}:{:02d}&equipamento={}".format(
                            reverse("agenda:agendar"), dia.isoformat(), hh, mm, equipamento_id
                        ),
                    }
                )
            m = fim_slot
    return vagas


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
    pode_agendar = request.user.is_superuser or request.user.is_gestor or request.user.is_professor
    agora = timezone.now()
    professor_logado_id = (
        request.user.professor.id if request.user.is_professor and hasattr(request.user, "professor") else None
    )

    colunas = []
    for equipamento in equipamentos:
        blocos = []
        ocupados = []
        for sessao in sessoes:
            if sessao.equipamento_id != equipamento.id:
                continue
            ocupados.append((_minutos(sessao.reserva_inicio, dia), _minutos(sessao.reserva_fim, dia)))
            eh_propria = professor_logado_id is not None and sessao.professor_id == professor_logado_id
            if professor_logado_id is not None:
                classe_sessao = "sessao propria" if eh_propria else "sessao outra"
            else:
                classe_sessao = "sessao"
            tem_preparo = sessao.reserva_inicio < sessao.inicio
            tem_troca = sessao.reserva_fim > sessao.fim
            if tem_preparo:
                blocos.append(_bloco("preparo", sessao.reserva_inicio, sessao.inicio, dia, inset_topo=True))
            if tem_troca:
                blocos.append(_bloco("troca", sessao.fim, sessao.reserva_fim, dia, inset_base=True))
            blocos.append(
                _bloco(
                    classe_sessao,
                    sessao.inicio,
                    sessao.fim,
                    dia,
                    titulo="{:%H:%M} – {:%H:%M} · {}".format(
                        timezone.localtime(sessao.inicio), timezone.localtime(sessao.fim), sessao.aluno
                    ),
                    subtitulo="{} · {}".format(sessao.professor, sessao.tipo),
                    inset_topo=not tem_preparo,
                    inset_base=not tem_troca,
                )
            )
        for bloqueio in bloqueios:
            if bloqueio.equipamento_id != equipamento.id:
                continue
            ocupados.append((_minutos(bloqueio.inicio, dia), _minutos(bloqueio.fim, dia)))
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
                    inset_topo=True,
                    inset_base=True,
                )
            )
        vagas = []
        if pode_agendar and equipamento.status == Equipamento.Status.ATIVO:
            vagas = _vagas_livres(ocupados, dia, equipamento.id, agora)
        colunas.append({"equipamento": equipamento, "blocos": blocos, "vagas": vagas})

    minutos_reservados = sum(
        (s.reserva_fim - s.reserva_inicio).total_seconds() / 60
        for s in sessoes
        if s.equipamento_id
    )
    capacidade = max(1, len(colunas)) * (HORA_FIM - HORA_INICIO) * 60
    # Faixa rolável de dias: uma semana antes e duas semanas depois do dia
    # visto, para o usuário arrastar/rolar lateralmente até a data desejada
    # sem precisar clicar em "‹"/"›" repetidas vezes.
    faixa_inicio = dia - timedelta(days=DIAS_ANTES_NA_FAIXA)

    return render(
        request,
        "agenda/grade.html",
        {
            "aba": "agenda",
            "data": dia,
            "hoje": hoje,
            "dia_anterior": dia - timedelta(days=1),
            "dia_seguinte": dia + timedelta(days=1),
            "faixa_dias": [
                {
                    "data": faixa_inicio + timedelta(days=i),
                    "selecionado": faixa_inicio + timedelta(days=i) == dia,
                }
                for i in range(DIAS_ANTES_NA_FAIXA + DIAS_DEPOIS_NA_FAIXA + 1)
            ],
            "horas": ["{:02d}:00".format(h) for h in range(HORA_INICIO, HORA_FIM)],
            "altura_hora": ALTURA_HORA,
            "altura_hora_menos1": ALTURA_HORA - 1,
            "altura_pista": (HORA_FIM - HORA_INICIO) * ALTURA_HORA,
            "colunas": colunas,
            "total_sessoes": len([s for s in sessoes]),
            "ocupacao": round(minutos_reservados / capacidade * 100),
            "pode_agendar": pode_agendar,
            "mostrar_legenda_propria": professor_logado_id is not None,
        },
    )
