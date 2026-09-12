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

from . import expediente, motor
from .models import BloqueioEquipamento, Sessao

HORA_INICIO = expediente.ABERTURA_HORA  # primeira hora exibida
HORA_FIM = expediente.FECHAMENTO_HORA   # última hora exibida (exclusiva)
ALTURA_HORA = 72         # px por hora
PX_POR_MIN = ALTURA_HORA / 60
SLOT_MIN = 30            # granularidade dos horários livres clicáveis
SLOT_MIN_MINIMO = 15     # não mostra sobra de vaga menor que isso no fim de um intervalo


GAP_PX = 3               # espaço visual entre reservas distintas (evita blocos "colados")
DIAS_ANTES_NA_FAIXA = 7  # quantos dias antes do selecionado aparecem na faixa rolável
DIAS_DEPOIS_NA_FAIXA = 14  # quantos dias depois do selecionado aparecem na faixa rolável

ALTURA_MIN_VAGA_PX = 40  # alvo mínimo de altura visual do bloco "vaga livre" (alvo de toque ~44px)


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


def _vagas_livres(ocupados, dia, equipamento_id, agora, professor_id=None):
    """Calcula os intervalos sem sessão/bloqueio na pista e devolve blocos
    clicáveis de SLOT_MIN minutos para permitir agendar direto na grade.
    Quando `professor_id` é informado (professor logado), o link já vem
    pré-preenchido com esse professor."""
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
            # Altura visual mínima (~40px) pra não ficar abaixo do alvo de
            # toque recomendado: só cresce quando este é o ÚLTIMO slot do
            # gap (nenhum outro slot vai nascer depois dele nesta janela —
            # mesma condição de `break` acima, olhando pro que resta após
            # `fim_slot`), senão cresceria por cima do próximo bloco "vaga"
            # vizinho. O teto é sempre o fim real do gap (`fim_gap`), nunca
            # inventa tempo livre que não existe.
            altura_px = (fim_slot - m) * PX_POR_MIN
            eh_ultimo_slot_do_gap = (fim_gap - fim_slot) < SLOT_MIN_MINIMO
            if eh_ultimo_slot_do_gap:
                altura_max_px = (fim_gap - m) * PX_POR_MIN
                altura_px = min(max(altura_px, ALTURA_MIN_VAGA_PX), altura_max_px)
            if momento >= agora:
                href = "{}?data={}&hora_inicio={:02d}:{:02d}&equipamento={}".format(
                    reverse("agenda:agendar"), dia.isoformat(), hh, mm, equipamento_id
                )
                if professor_id is not None:
                    href += "&professor={}".format(professor_id)
                vagas.append(
                    {
                        "top": "{:.1f}".format(m * PX_POR_MIN),
                        "altura": "{:.1f}".format(altura_px),
                        "titulo": "{:02d}:{:02d}".format(hh, mm),
                        "href": href,
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

    sessoes = list(
        Sessao.objects.exclude(status=Sessao.Status.CANCELADA)
        .filter(reserva_inicio__lt=fim_dia, reserva_fim__gt=inicio_dia)
        .select_related("aluno", "professor__usuario", "tipo", "equipamento")
    )
    bloqueios = list(BloqueioEquipamento.objects.filter(inicio__lt=fim_dia, fim__gt=inicio_dia))

    equipamentos = list(Equipamento.objects.exclude(status=Equipamento.Status.INATIVO))
    # Equipamento ativo primeiro, em manutenção depois — `sorted` é estável,
    # então dentro de cada grupo mantém a ordem original (por nome, do
    # `Meta.ordering` do model).
    equipamentos = sorted(equipamentos, key=lambda e: e.status != Equipamento.Status.ATIVO)
    pode_agendar = request.user.is_superuser or request.user.is_gestor or request.user.is_professor
    agora = timezone.now()

    # Professor logado (se houver): usado para pré-preencher o formulário ao
    # clicar numa vaga livre da grade (item 7) — independente do filtro
    # `?professor=` abaixo, que é sobre DESTAQUE visual, não sobre quem está
    # logado.
    professor_logado = (
        request.user.professor if request.user.is_professor and hasattr(request.user, "professor") else None
    )

    # Professor em destaque na grade: o filtro explícito `?professor=` tem
    # prioridade; sem filtro, cai no comportamento antigo de destacar as
    # sessões do próprio professor logado.
    professor_destaque_id = None
    filtro_professor_id = request.GET.get("professor")
    if filtro_professor_id:
        try:
            professor_destaque_id = int(filtro_professor_id)
        except (TypeError, ValueError):
            professor_destaque_id = None
    elif professor_logado is not None:
        professor_destaque_id = professor_logado.id
    filtro_professor_ativo = professor_destaque_id is not None and bool(filtro_professor_id)

    resumo = motor.resumo_do_dia(dia)

    # Menor `inicio_min` entre todas as sessões/bloqueios do dia, em todas as
    # colunas — usado como posição de fallback pro auto-scroll inicial (item
    # 7) quando não é hoje (sem "linha do agora" pra mirar).
    menor_inicio_ocupado_min = None

    colunas = []
    for equipamento in equipamentos:
        blocos = []
        ocupados = []
        for sessao in sessoes:
            if sessao.equipamento_id != equipamento.id:
                continue
            ocupados.append((_minutos(sessao.reserva_inicio, dia), _minutos(sessao.reserva_fim, dia)))
            eh_destaque = professor_destaque_id is not None and sessao.professor_id == professor_destaque_id
            if professor_destaque_id is not None:
                classe_sessao = "sessao propria" if eh_destaque else "sessao outra"
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
        if ocupados:
            candidato = min(inicio_min for inicio_min, _ in ocupados)
            if menor_inicio_ocupado_min is None or candidato < menor_inicio_ocupado_min:
                menor_inicio_ocupado_min = candidato

        vagas = []
        if pode_agendar and equipamento.status == Equipamento.Status.ATIVO:
            professor_id_para_vaga = professor_logado.id if professor_logado is not None else None
            vagas = _vagas_livres(ocupados, dia, equipamento.id, agora, professor_id=professor_id_para_vaga)

        colunas.append(
            {
                "equipamento": equipamento,
                "blocos": blocos,
                "vagas": vagas,
            }
        )

    # Linha de professores do dia: um chip por professor com sessão marcada
    # no dia, priorizando quem tem sessão pra não poluir a linha com todo o
    # quadro de professores ativos.
    professores_do_dia = {}
    minutos_ocupados_professor = {}
    for sessao in sessoes:
        professores_do_dia.setdefault(sessao.professor_id, sessao.professor)
        minutos = (sessao.prof_fim - sessao.prof_inicio).total_seconds() / 60
        minutos_ocupados_professor[sessao.professor_id] = (
            minutos_ocupados_professor.get(sessao.professor_id, 0) + minutos
        )
    linha_professores = []
    for professor_id, professor in professores_do_dia.items():
        qtd = resumo["por_professor"].get(str(professor), 0)
        # Heurística simples (sem N+1): se as sessões do professor não
        # cobrem o expediente inteiro, sobra tempo livre em algum ponto do
        # dia. Não garante um horário específico livre (isso é o que
        # `motor.buscar_vagas` faz, mas custaria uma consulta por professor
        # por tipo de sessão só para pintar um chip).
        livre = minutos_ocupados_professor.get(professor_id, 0) < expediente.MINUTOS_EXPEDIENTE
        linha_professores.append(
            {
                "professor": professor,
                "qtd": qtd,
                "livre": livre,
                "destaque": professor_id == professor_destaque_id,
                "href": "?data={}&professor={}".format(dia.isoformat(), professor_id),
            }
        )
    linha_professores.sort(key=lambda item: str(item["professor"]))

    # Linha do "agora": só desenhada no dia de hoje e dentro do expediente.
    agora_local = timezone.localtime(agora)
    mostrar_linha_agora = dia == hoje and expediente.ABERTURA <= agora_local.time() < expediente.FECHAMENTO
    linha_agora_top = "{:.1f}".format(_offset(agora, dia)) if mostrar_linha_agora else None

    # Auto-scroll ao abrir a página (item 7 da auditoria mobile): quando não
    # há "linha do agora" pra mirar (outro dia, ou hoje fora do expediente),
    # cai pro topo do primeiro bloco ocupado do dia entre todas as colunas —
    # evita abrir a grade sempre no início do expediente (07:00), bem acima
    # da dobra em qualquer dia com sessão marcada.
    scroll_inicial_top = None
    if not mostrar_linha_agora and menor_inicio_ocupado_min is not None:
        scroll_inicial_top = "{:.1f}".format(menor_inicio_ocupado_min * PX_POR_MIN)

    # Faixa rolável de dias: uma semana antes e duas semanas depois do dia
    # visto, para o usuário arrastar/rolar lateralmente até a data desejada
    # sem precisar clicar em "‹"/"›" repetidas vezes.
    faixa_inicio = dia - timedelta(days=DIAS_ANTES_NA_FAIXA)
    faixa_fim = dia + timedelta(days=DIAS_DEPOIS_NA_FAIXA)
    contagem_faixa = motor.contagem_por_dia(faixa_inicio, faixa_fim)

    faixa_dias = []
    for i in range(DIAS_ANTES_NA_FAIXA + DIAS_DEPOIS_NA_FAIXA + 1):
        data_dia = faixa_inicio + timedelta(days=i)
        qtd_dia = contagem_faixa.get(data_dia, 0)
        faixa_dias.append(
            {
                "data": data_dia,
                "selecionado": data_dia == dia,
                "qtd": qtd_dia,
                "nivel": motor.nivel_de_movimento(qtd_dia),
            }
        )

    return render(
        request,
        "agenda/grade.html",
        {
            "aba": "agenda",
            "data": dia,
            "hoje": hoje,
            "dia_eh_hoje": dia == hoje,
            "dia_anterior": dia - timedelta(days=1),
            "dia_seguinte": dia + timedelta(days=1),
            "faixa_dias": faixa_dias,
            "horas": ["{:02d}:00".format(h) for h in range(HORA_INICIO, HORA_FIM)],
            "altura_hora": ALTURA_HORA,
            "altura_hora_menos1": ALTURA_HORA - 1,
            "altura_pista": (HORA_FIM - HORA_INICIO) * ALTURA_HORA,
            "colunas": colunas,
            "linha_professores": linha_professores,
            "mostrar_linha_agora": mostrar_linha_agora,
            "linha_agora_top": linha_agora_top,
            "scroll_inicial_top": scroll_inicial_top,
            "pode_agendar": pode_agendar,
            "mostrar_legenda_propria": professor_destaque_id is not None,
            "filtro_professor_ativo": filtro_professor_ativo,
        },
    )
