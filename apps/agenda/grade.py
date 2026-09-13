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
from .permissoes import _digitos, _pode_gerenciar_sessao

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


def _minutos_de_hora(hora):
    """Minuto (clipado à janela do dia) de um horário sem data (`time`)
    dentro da pista do dia — mesma referência de `_minutos`, usada para
    converter as janelas de `DisponibilidadeProfessor` (que não têm data,
    só hora de início/fim) para o mesmo sistema de minutos-desde-a-abertura
    usado pelos gaps livres do equipamento."""
    minutos = (hora.hour - HORA_INICIO) * 60 + hora.minute
    limite = (HORA_FIM - HORA_INICIO) * 60
    return max(0, min(minutos, limite))


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


def _gaps_livres(ocupados, limite):
    """Intervalos (inicio_min, fim_min) sem sessão/bloqueio dentro do
    expediente, a partir da lista de intervalos ocupados de uma coluna."""
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
    return livres_min


def _janelas_disponibilidade_professor(professor, dia):
    """Janelas (inicio_min, fim_min) em que o professor está disponível
    nesse dia da semana, no mesmo sistema de minutos-desde-a-abertura dos
    gaps livres do equipamento.

    `None` = sem NENHUMA `DisponibilidadeProfessor` cadastrada (em
    qualquer dia) = sem restrição, mesma regra de
    `motor.professor_dentro_da_disponibilidade`. Lista vazia = tem
    disponibilidade cadastrada em outros dias da semana, mas nenhuma
    neste — indisponível o dia inteiro."""
    if not professor.disponibilidades.exists():
        return None
    return [
        (_minutos_de_hora(d.hora_inicio), _minutos_de_hora(d.hora_fim))
        for d in professor.disponibilidades.filter(dia_semana=dia.weekday())
    ]


def _intersecta_com_disponibilidade(gaps, janelas_disponibilidade):
    """Interseção dos gaps livres do equipamento com as janelas de
    disponibilidade do professor logado. `janelas_disponibilidade=None`
    (sem restrição) devolve os gaps como vieram."""
    if janelas_disponibilidade is None:
        return gaps
    resultado = []
    for g_inicio, g_fim in gaps:
        for j_inicio, j_fim in janelas_disponibilidade:
            inicio = max(g_inicio, j_inicio)
            fim = min(g_fim, j_fim)
            if inicio < fim:
                resultado.append((inicio, fim))
    return sorted(resultado)


def _slots_do_gap(inicio_gap, fim_gap, dia, equipamento_id, agora, professor_id):
    """Blocos clicáveis de SLOT_MIN minutos dentro de UM intervalo livre —
    usados tanto na lista "por slot" (desktop, `_vagas_livres`) quanto
    dentro do bottom sheet de cada intervalo consolidado (mobile,
    `_vagas_consolidadas`)."""
    slots = []
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
            slots.append(
                {
                    "top": "{:.1f}".format(m * PX_POR_MIN),
                    "altura": "{:.1f}".format(altura_px),
                    "titulo": "{:02d}:{:02d}".format(hh, mm),
                    "href": href,
                }
            )
        m = fim_slot
    return slots


def _vagas_livres(ocupados, dia, equipamento_id, agora, professor_id=None, janelas_disponibilidade=None):
    """Calcula os intervalos sem sessão/bloqueio na pista e devolve blocos
    clicáveis de SLOT_MIN minutos para permitir agendar direto na grade
    (usado no desktop — no mobile, ver `_vagas_consolidadas`). Quando
    `professor_id` é informado (professor logado), o link já vem
    pré-preenchido com esse professor. `janelas_disponibilidade`, quando
    informado (não `None`), restringe os intervalos à disponibilidade
    cadastrada do professor logado (ver `_janelas_disponibilidade_professor`)."""
    limite = (HORA_FIM - HORA_INICIO) * 60
    gaps = _intersecta_com_disponibilidade(_gaps_livres(ocupados, limite), janelas_disponibilidade)

    vagas = []
    for inicio_gap, fim_gap in gaps:
        vagas.extend(_slots_do_gap(inicio_gap, fim_gap, dia, equipamento_id, agora, professor_id))
    return vagas


def _vagas_consolidadas(ocupados, dia, equipamento_id, agora, professor_id=None, janelas_disponibilidade=None):
    """Um bloco por intervalo livre CONTÍNUO (em vez de um por slot de
    30min) — usado no mobile pra não poluir a coluna com dezenas de
    botões "+ HH:MM" num dia parado. Cada bloco cobre visualmente o
    intervalo inteiro e carrega a lista de slots daquele intervalo
    (`slots`, mesmo formato de `_vagas_livres`) pra preencher o bottom
    sheet aberto ao tocar. Intervalos sem nenhum slot clicável (todo no
    passado, ou curto demais) não geram bloco."""
    limite = (HORA_FIM - HORA_INICIO) * 60
    gaps = _intersecta_com_disponibilidade(_gaps_livres(ocupados, limite), janelas_disponibilidade)

    consolidadas = []
    for indice, (inicio_gap, fim_gap) in enumerate(gaps):
        slots = _slots_do_gap(inicio_gap, fim_gap, dia, equipamento_id, agora, professor_id)
        if not slots:
            continue
        hh_inicio, mm_inicio = divmod(HORA_INICIO * 60 + inicio_gap, 60)
        hh_fim, mm_fim = divmod(HORA_INICIO * 60 + fim_gap, 60)
        consolidadas.append(
            {
                "id": "folha-vaga-{}-{}".format(equipamento_id, indice),
                "top": "{:.1f}".format(inicio_gap * PX_POR_MIN),
                "altura": "{:.1f}".format(max((fim_gap - inicio_gap) * PX_POR_MIN, ALTURA_MIN_VAGA_PX)),
                "titulo": "Livre {:02d}:{:02d}–{:02d}:{:02d}".format(hh_inicio, mm_inicio, hh_fim, mm_fim),
                "slots": slots,
            }
        )
    return consolidadas


def _cartao_sessao(usuario, sessao, aluno_logado):
    """Item "sessao" da linha do tempo (Etapa 2d): mesma regra de
    privacidade (LGPD) e os mesmos dados de ação (`sessao_id`,
    `pode_gerenciar`, link do WhatsApp) já usados pelos blocos de sessão
    da grade por equipamento (ver `grade()`) — só reformatados como
    cartão de lista em vez de bloco posicionado em pixel."""
    eh_sessao_de_outro_aluno = aluno_logado is not None and sessao.aluno_id != aluno_logado.id
    if eh_sessao_de_outro_aluno:
        return {
            "tipo": "sessao",
            "hora_inicio": "{:%H:%M}".format(timezone.localtime(sessao.inicio)),
            "hora_fim": "{:%H:%M}".format(timezone.localtime(sessao.fim)),
            "titulo": "Ocupado",
            "subtitulo": "",
            "equipamento": sessao.equipamento,
        }

    cartao = {
        "tipo": "sessao",
        "hora_inicio": "{:%H:%M}".format(timezone.localtime(sessao.inicio)),
        "hora_fim": "{:%H:%M}".format(timezone.localtime(sessao.fim)),
        "titulo": str(sessao.aluno),
        "subtitulo": "{} · {}".format(sessao.professor, sessao.tipo),
        "equipamento": sessao.equipamento,
        "sessao": sessao,
        "sessao_id": sessao.pk,
    }
    pode_gerenciar = _pode_gerenciar_sessao(usuario, sessao)
    cartao["pode_gerenciar"] = pode_gerenciar
    if pode_gerenciar:
        digitos = _digitos(sessao.aluno.telefone)
        cartao["link_whatsapp"] = f"https://wa.me/55{digitos}" if digitos else None
    return cartao


def _separadores_livres(sessoes, bloqueios, equipamentos_ativos, dia, agora, professor_id, janelas_disponibilidade):
    """Separadores "Livre HH:MM–HH:MM · N equipamentos" da linha do tempo
    (Etapa 2d).

    Sweep-line sobre os limites de RESERVA de cada sessão (não o horário
    da sessão em si — a reserva já inclui preparo/troca) e de cada
    bloqueio do dia: os pontos de corte (mais início/fim do expediente)
    dividem o dia em segmentos; para cada segmento, conta quantos
    equipamentos ATIVOS não têm nenhuma reserva sobrepondo aquele
    intervalo inteiro (mesma checagem de sobreposição de
    `motor._periodos_se_sobrepoem`, aqui em minutos-desde-a-abertura em
    vez de datetimes — a função não se importa com o tipo, só compara
    com `<`). Segmentos com contagem zero, ou mais curtos que `SLOT_MIN`,
    não geram separador."""
    limite = (HORA_FIM - HORA_INICIO) * 60
    ocupacoes = {}
    for sessao in sessoes:
        ocupacoes.setdefault(sessao.equipamento_id, []).append(
            (_minutos(sessao.reserva_inicio, dia), _minutos(sessao.reserva_fim, dia))
        )
    for bloqueio in bloqueios:
        ocupacoes.setdefault(bloqueio.equipamento_id, []).append(
            (_minutos(bloqueio.inicio, dia), _minutos(bloqueio.fim, dia))
        )

    pontos = {0, limite}
    for intervalos in ocupacoes.values():
        for inicio_min, fim_min in intervalos:
            pontos.add(max(0, min(inicio_min, limite)))
            pontos.add(max(0, min(fim_min, limite)))
    pontos = sorted(pontos)

    segmentos = [(pontos[i], pontos[i + 1]) for i in range(len(pontos) - 1) if pontos[i] < pontos[i + 1]]
    # Restringe os segmentos à disponibilidade cadastrada do professor
    # logado ANTES de contar equipamentos livres — um intervalo fora da
    # disponibilidade dele nem entra na contagem, mesma regra já aplicada
    # às vagas por equipamento (`_vagas_consolidadas`).
    segmentos = _intersecta_com_disponibilidade(segmentos, janelas_disponibilidade)

    separadores = []
    for inicio_seg, fim_seg in segmentos:
        if fim_seg - inicio_seg < SLOT_MIN:
            continue
        equipamentos_livres = [
            equipamento
            for equipamento in equipamentos_ativos
            if not any(
                motor._periodos_se_sobrepoem(inicio_seg, fim_seg, oc_inicio, oc_fim)
                for oc_inicio, oc_fim in ocupacoes.get(equipamento.id, [])
            )
        ]
        if not equipamentos_livres:
            continue
        hh_inicio, mm_inicio = divmod(HORA_INICIO * 60 + inicio_seg, 60)
        hh_fim, mm_fim = divmod(HORA_INICIO * 60 + fim_seg, 60)
        grupos = [
            {
                "equipamento": equipamento,
                "slots": _slots_do_gap(inicio_seg, fim_seg, dia, equipamento.id, agora, professor_id),
            }
            for equipamento in equipamentos_livres
        ]
        separadores.append(
            {
                "tipo": "livre",
                "inicio_min": inicio_seg,
                "inicio_texto": "{:02d}:{:02d}".format(hh_inicio, mm_inicio),
                "fim_texto": "{:02d}:{:02d}".format(hh_fim, mm_fim),
                "qtd_equipamentos": len(equipamentos_livres),
                "grupos": grupos,
            }
        )
    return separadores


def _montar_linha_tempo(usuario, sessoes, bloqueios, equipamentos, dia, agora, professor_id, aluno_logado, janelas_disponibilidade):
    """Lista única, em ordem cronológica, de cartões de sessão e
    separadores "livre" intercalados — a visão "Linha do tempo" da
    Etapa 2d (alternativa mobile-first à grade por equipamento)."""
    equipamentos_ativos = [e for e in equipamentos if e.status == Equipamento.Status.ATIVO]
    separadores = _separadores_livres(
        sessoes, bloqueios, equipamentos_ativos, dia, agora, professor_id, janelas_disponibilidade
    )

    itens = [(_minutos(sessao.inicio, dia), _cartao_sessao(usuario, sessao, aluno_logado)) for sessao in sessoes]
    itens += [(separador["inicio_min"], separador) for separador in separadores]
    itens.sort(key=lambda item: item[0])
    return [item[1] for item in itens]


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

    # Privacidade (LGPD): aluno logado só pode ver detalhes (hora, nome,
    # professor, tipo) das PRÓPRIAS sessões. Sessão de outro aluno aparece
    # como bloco "Ocupado", sem nenhuma informação identificável de
    # terceiros — gestor e professor continuam vendo tudo normalmente.
    aluno_logado = (
        request.user.aluno if request.user.is_aluno and hasattr(request.user, "aluno") else None
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

    # Disponibilidade cadastrada do professor logado (item 2 da Etapa 2b):
    # restringe as vagas mostradas pra ele só ao horário em que realmente
    # está disponível, mesmo que o equipamento esteja fisicamente livre.
    # `None` = sem restrição (mesma regra de
    # `motor.professor_dentro_da_disponibilidade`).
    janelas_disponibilidade = (
        _janelas_disponibilidade_professor(professor_logado, dia) if professor_logado is not None else None
    )

    # A grade não mostra mais "próxima vaga" (KPI removido) — pula o
    # cálculo mais caro de resumo_do_dia, que aqui só serve pra
    # `linha_professores` (via `por_professor`).
    resumo = motor.resumo_do_dia(dia, incluir_proxima_vaga=False)

    # Linha do tempo (Etapa 2d): visão alternativa, mobile-first, da mesma
    # `sessoes`/`bloqueios`/`equipamentos` já carregados acima — reaproveita
    # os mesmos dados, sem requery.
    linha_tempo = _montar_linha_tempo(
        request.user, sessoes, bloqueios, equipamentos, dia, agora,
        professor_logado.id if professor_logado is not None else None,
        aluno_logado, janelas_disponibilidade,
    )

    # Toggle manual "Linha do tempo / Grade" (`?visao=lista`/`?visao=grade`):
    # qualquer outro valor (ou ausência do parâmetro) deixa a escolha padrão
    # por tela a cargo do CSS (mobile = linha do tempo, desktop = grade).
    visao_param = request.GET.get("visao")
    visao_forcada = visao_param if visao_param in ("lista", "grade") else None

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
            eh_sessao_de_outro_aluno = aluno_logado is not None and sessao.aluno_id != aluno_logado.id
            if eh_sessao_de_outro_aluno:
                titulo_sessao = "Ocupado"
                subtitulo_sessao = ""
            else:
                titulo_sessao = "{:%H:%M} – {:%H:%M} · {}".format(
                    timezone.localtime(sessao.inicio), timezone.localtime(sessao.fim), sessao.aluno
                )
                subtitulo_sessao = "{} · {}".format(sessao.professor, sessao.tipo)
            bloco_sessao = _bloco(
                classe_sessao,
                sessao.inicio,
                sessao.fim,
                dia,
                titulo=titulo_sessao,
                subtitulo=subtitulo_sessao,
                inset_topo=not tem_preparo,
                inset_base=not tem_troca,
            )
            # Dados de ação do bottom sheet (Etapa 2c-ii): só quando a
            # sessão NÃO é o caso "Ocupado" de outro aluno — privacidade
            # (LGPD) já aplicada acima continua valendo, o bloco "Ocupado"
            # não ganha `sessao_id` nem nenhuma informação de ação.
            if not eh_sessao_de_outro_aluno:
                bloco_sessao["sessao_id"] = sessao.pk
                # Objeto completo, pro bottom sheet montar o resumo (status,
                # professor, tipo, equipamento) sem precisar duplicar cada
                # campo em chave separada — mesmo padrão de acesso que
                # `templates/agenda/detalhe.html` já usa via `sessao.*`.
                bloco_sessao["sessao"] = sessao
                pode_gerenciar = _pode_gerenciar_sessao(request.user, sessao)
                bloco_sessao["pode_gerenciar"] = pode_gerenciar
                if pode_gerenciar:
                    digitos = _digitos(sessao.aluno.telefone)
                    bloco_sessao["link_whatsapp"] = f"https://wa.me/55{digitos}" if digitos else None
            blocos.append(bloco_sessao)
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
        vagas_consolidadas = []
        if pode_agendar and equipamento.status == Equipamento.Status.ATIVO:
            professor_id_para_vaga = professor_logado.id if professor_logado is not None else None
            vagas = _vagas_livres(
                ocupados, dia, equipamento.id, agora,
                professor_id=professor_id_para_vaga, janelas_disponibilidade=janelas_disponibilidade,
            )
            vagas_consolidadas = _vagas_consolidadas(
                ocupados, dia, equipamento.id, agora,
                professor_id=professor_id_para_vaga, janelas_disponibilidade=janelas_disponibilidade,
            )

        colunas.append(
            {
                "equipamento": equipamento,
                "blocos": blocos,
                "vagas": vagas,
                "vagas_consolidadas": vagas_consolidadas,
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
            "linha_tempo": linha_tempo,
            "visao_forcada": visao_forcada,
        },
    )
