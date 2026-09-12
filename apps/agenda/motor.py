"""
Motor de regras da agenda: calcula as janelas de reserva (equipamento) e
de ocupação do professor a partir da sessão real + preparo/troca do
tipo de sessão, e verifica se o horário pedido é possível — professor
ativo, habilitado ao tipo de sessão, dentro da disponibilidade cadastrada
e sem conflito de horário; aluno sem conflito de horário; equipamento
exigido quando o tipo de sessão precisa dele, ativo e livre.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.cadastros.models import Equipamento, Professor, TipoSessao

from . import expediente
from .models import BloqueioEquipamento, Sessao

FUSO_SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def calcular_janelas(inicio, fim, tipo_sessao):
    """Calcula (reserva_inicio, reserva_fim, prof_inicio, prof_fim) para uma sessão."""
    preparo = timedelta(minutes=tipo_sessao.preparo_min)
    troca = timedelta(minutes=tipo_sessao.troca_min)

    reserva_inicio = inicio - preparo
    reserva_fim = fim + troca

    if tipo_sessao.professor_no_preparo:
        prof_inicio, prof_fim = reserva_inicio, reserva_fim
    else:
        prof_inicio, prof_fim = inicio, fim

    return reserva_inicio, reserva_fim, prof_inicio, prof_fim


def _periodos_se_sobrepoem(inicio_a, fim_a, inicio_b, fim_b):
    return inicio_a < fim_b and inicio_b < fim_a


def professor_habilitado(professor, tipo_sessao):
    """O professor precisa estar explicitamente habilitado ao tipo de sessão."""
    return professor.tipos_habilitados.filter(pk=tipo_sessao.pk).exists()


def professor_dentro_da_disponibilidade(professor, prof_inicio, prof_fim):
    """Se o professor tiver disponibilidades cadastradas, a sessão precisa caber
    inteira em uma delas. Sem nenhuma disponibilidade cadastrada, não há restrição
    (permite operar antes de o gestor configurar a agenda semanal de cada um)."""
    disponibilidades = list(professor.disponibilidades.all())
    if not disponibilidades:
        return True
    if prof_inicio.date() != prof_fim.date():
        return False

    dia_semana = prof_inicio.weekday()
    hora_inicio, hora_fim = prof_inicio.time(), prof_fim.time()
    return any(
        d.dia_semana == dia_semana and d.hora_inicio <= hora_inicio and hora_fim <= d.hora_fim
        for d in disponibilidades
    )


def equipamento_ativo(equipamento):
    return equipamento is None or equipamento.status == equipamento.Status.ATIVO


def professor_disponivel(professor, prof_inicio, prof_fim, excluir_sessao_id=None):
    sessoes = (
        Sessao.objects.filter(professor=professor, prof_inicio__lt=prof_fim, prof_fim__gt=prof_inicio)
        .exclude(status=Sessao.Status.CANCELADA)
    )
    if excluir_sessao_id:
        sessoes = sessoes.exclude(pk=excluir_sessao_id)

    for sessao in sessoes:
        if _periodos_se_sobrepoem(prof_inicio, prof_fim, sessao.prof_inicio, sessao.prof_fim):
            return False
    return True


def aluno_disponivel(aluno, inicio, fim, excluir_sessao_id=None):
    """O aluno não pode estar em duas sessões (não canceladas) no mesmo horário."""
    sessoes = (
        Sessao.objects.filter(aluno=aluno, inicio__lt=fim, fim__gt=inicio)
        .exclude(status=Sessao.Status.CANCELADA)
    )
    if excluir_sessao_id:
        sessoes = sessoes.exclude(pk=excluir_sessao_id)

    for sessao in sessoes:
        if _periodos_se_sobrepoem(inicio, fim, sessao.inicio, sessao.fim):
            return False
    return True


def equipamento_disponivel(equipamento, reserva_inicio, reserva_fim, excluir_sessao_id=None):
    if equipamento is None:
        return True

    sessoes = (
        Sessao.objects.filter(
            equipamento=equipamento, reserva_inicio__lt=reserva_fim, reserva_fim__gt=reserva_inicio
        ).exclude(status=Sessao.Status.CANCELADA)
    )
    if excluir_sessao_id:
        sessoes = sessoes.exclude(pk=excluir_sessao_id)

    for sessao in sessoes:
        if _periodos_se_sobrepoem(reserva_inicio, reserva_fim, sessao.reserva_inicio, sessao.reserva_fim):
            return False

    for bloqueio in equipamento.bloqueios.all():
        if _periodos_se_sobrepoem(reserva_inicio, reserva_fim, bloqueio.inicio, bloqueio.fim):
            return False
    return True


def motivo_indisponibilidade(professor, equipamento, inicio, fim, tipo_sessao, aluno, excluir_sessao_id=None):
    """Retorna uma mensagem explicando por que o horário não pode ser confirmado,
    ou None se professor, aluno e equipamento estiverem livres e aptos."""
    if not professor.ativo:
        return f"{professor} não está ativo."

    if not professor_habilitado(professor, tipo_sessao):
        return f'{professor} não está habilitado para o tipo de sessão "{tipo_sessao}".'

    if tipo_sessao.requer_equipamento and equipamento is None:
        return f'O tipo de sessão "{tipo_sessao}" exige um equipamento.'

    reserva_inicio, reserva_fim, prof_inicio, prof_fim = calcular_janelas(inicio, fim, tipo_sessao)

    if not professor_dentro_da_disponibilidade(professor, prof_inicio, prof_fim):
        return f"{professor} não tem disponibilidade cadastrada nesse horário."

    if not professor_disponivel(professor, prof_inicio, prof_fim, excluir_sessao_id):
        return f"{professor} já tem outra sessão nesse horário."

    if not aluno_disponivel(aluno, inicio, fim, excluir_sessao_id):
        return f"{aluno} já tem outra sessão nesse horário."

    if not equipamento_ativo(equipamento):
        return f"{equipamento} está {equipamento.get_status_display().lower()} e não pode ser reservado."

    if not equipamento_disponivel(equipamento, reserva_inicio, reserva_fim, excluir_sessao_id):
        return f"{equipamento} já está reservado ou bloqueado nesse horário."

    return None


def verificar_disponibilidade(professor, equipamento, inicio, fim, tipo_sessao, aluno, excluir_sessao_id=None):
    """Retorna True se professor, aluno e equipamento estiverem livres e aptos no horário pedido."""
    return (
        motivo_indisponibilidade(professor, equipamento, inicio, fim, tipo_sessao, aluno, excluir_sessao_id)
        is None
    )


PASSO_SUGESTAO_MIN = 30
LIMITE_SUGESTOES = 6

_LIMITES_PERIODO = {
    "manha": (None, time(12, 0)),
    "tarde": (time(12, 0), time(18, 0)),
    "noite": (time(18, 0), None),
}


def _limites_periodo(periodo):
    if periodo is None:
        return None, None
    if periodo not in _LIMITES_PERIODO:
        raise ValueError(f'Período inválido: "{periodo}". Use "manha", "tarde" ou "noite".')
    return _LIMITES_PERIODO[periodo]


def _momentos_candidatos(dia, duracao, abertura, fechamento, passo, hora_desejada, periodo):
    """Lista (ordenada por proximidade do horário desejado) de horários de
    início candidatos dentro do expediente do dia, respeitando `periodo`
    (manhã/tarde/noite) e descartando horários que já passaram."""
    inicio_expediente = timezone.make_aware(datetime.combine(dia, abertura))
    fim_expediente = timezone.make_aware(datetime.combine(dia, fechamento))
    agora = timezone.now()
    alvo = (
        timezone.make_aware(datetime.combine(dia, hora_desejada))
        if hora_desejada
        else max(inicio_expediente, agora)
    )
    periodo_inicio, periodo_fim = _limites_periodo(periodo)

    momentos = []
    momento = inicio_expediente
    while momento + duracao <= fim_expediente:
        dentro_do_periodo = (periodo_inicio is None or momento.time() >= periodo_inicio) and (
            periodo_fim is None or momento.time() < periodo_fim
        )
        if momento >= agora and dentro_do_periodo:
            momentos.append(momento)
        momento += passo
    momentos.sort(key=lambda m: (abs((m - alvo).total_seconds()), m))
    return momentos


def _vagas_professor(
    *,
    professor,
    tipo_sessao,
    dia,
    equipamento_preferido=None,
    equipamentos=None,
    hora_desejada=None,
    periodo=None,
    abertura=None,
    fechamento=None,
    passo_min=None,
    limite=LIMITE_SUGESTOES,
):
    """Agenda inteligente para UM professor: varre o expediente do dia e
    devolve até `limite` combinações (equipamento, início, fim) livres para
    esse professor e tipo de sessão — no máximo uma por equipamento,
    priorizando o equipamento preferido e o horário mais próximo do
    desejado. Devolve lista vazia se o professor não estiver habilitado
    para o tipo de sessão.

    Compartilhado por `sugerir_horarios` (uso externo, professor fixo) e
    `buscar_vagas` (varre vários professores). Para não repetir consultas
    ao banco a cada combinação de horário × equipamento, as sessões/
    disponibilidades do professor e as sessões/bloqueios de cada
    equipamento são carregados uma única vez e as sobreposições são
    checadas em memória."""
    if not professor_habilitado(professor, tipo_sessao):
        return []

    abertura = abertura if abertura is not None else expediente.ABERTURA
    fechamento = fechamento if fechamento is not None else expediente.FECHAMENTO
    passo_min = passo_min if passo_min is not None else PASSO_SUGESTAO_MIN

    duracao = timedelta(minutes=tipo_sessao.duracao_min)
    passo = timedelta(minutes=passo_min)
    momentos = _momentos_candidatos(dia, duracao, abertura, fechamento, passo, hora_desejada, periodo)

    if equipamentos is None:
        equipamentos = list(Equipamento.objects.filter(status=Equipamento.Status.ATIVO).order_by("nome"))
    else:
        equipamentos = [e for e in equipamentos if e.status == Equipamento.Status.ATIVO]
    if equipamento_preferido is not None:
        equipamentos.sort(key=lambda e: e.pk != equipamento_preferido.pk)

    disponibilidades = list(professor.disponibilidades.all())
    sessoes_professor = list(
        Sessao.objects.filter(professor=professor).exclude(status=Sessao.Status.CANCELADA)
    )
    sessoes_equipamento = {}
    bloqueios_equipamento = {}
    for equipamento in equipamentos:
        sessoes_equipamento[equipamento.pk] = list(
            Sessao.objects.filter(equipamento=equipamento).exclude(status=Sessao.Status.CANCELADA)
        )
        bloqueios_equipamento[equipamento.pk] = list(equipamento.bloqueios.all())

    sugestoes = []
    usados = set()
    for momento in momentos:
        fim = momento + duracao
        reserva_inicio, reserva_fim, prof_inicio, prof_fim = calcular_janelas(momento, fim, tipo_sessao)

        if disponibilidades and (
            prof_inicio.date() != prof_fim.date()
            or not any(
                d.dia_semana == prof_inicio.weekday()
                and d.hora_inicio <= prof_inicio.time()
                and prof_fim.time() <= d.hora_fim
                for d in disponibilidades
            )
        ):
            continue

        if any(
            _periodos_se_sobrepoem(prof_inicio, prof_fim, sessao.prof_inicio, sessao.prof_fim)
            for sessao in sessoes_professor
        ):
            continue

        for equipamento in equipamentos:
            if equipamento.pk in usados:
                continue

            conflito = any(
                _periodos_se_sobrepoem(reserva_inicio, reserva_fim, sessao.reserva_inicio, sessao.reserva_fim)
                for sessao in sessoes_equipamento[equipamento.pk]
            ) or any(
                _periodos_se_sobrepoem(reserva_inicio, reserva_fim, bloqueio.inicio, bloqueio.fim)
                for bloqueio in bloqueios_equipamento[equipamento.pk]
            )
            if conflito:
                continue

            sugestoes.append({"equipamento": equipamento, "inicio": momento, "fim": fim})
            usados.add(equipamento.pk)
            if len(sugestoes) >= limite:
                return sugestoes
    return sugestoes


def sugerir_horarios(
    *,
    professor,
    tipo_sessao,
    dia,
    equipamento_preferido=None,
    hora_desejada=None,
    abertura=None,
    fechamento=None,
    passo_min=None,
    limite=LIMITE_SUGESTOES,
):
    """Agenda inteligente: varre o expediente do dia e devolve até `limite`
    combinações (equipamento, início, fim) livres para o professor e tipo de
    sessão pedidos — no máximo uma por equipamento, priorizando o equipamento
    preferido e o horário mais próximo do desejado. Devolve lista vazia se o
    professor não estiver habilitado para o tipo de sessão."""
    return _vagas_professor(
        professor=professor,
        tipo_sessao=tipo_sessao,
        dia=dia,
        equipamento_preferido=equipamento_preferido,
        hora_desejada=hora_desejada,
        abertura=abertura,
        fechamento=fechamento,
        passo_min=passo_min,
        limite=limite,
    )


def buscar_vagas(
    *,
    tipo_sessao,
    dia,
    professor=None,
    equipamento=None,
    hora_desejada=None,
    periodo=None,
    limite=8,
):
    """Vagas livres no dia para o tipo de sessão pedido, no formato
    {"professor", "equipamento", "inicio", "fim"}.

    Sem `professor` fixado, varre todos os professores ativos habilitados
    para o tipo de sessão (em vez de um único professor fixo). `periodo`
    filtra os horários candidatos do dia: "manha" (antes das 12h), "tarde"
    (12h–18h) ou "noite" (depois das 18h), dentro do expediente do estúdio."""
    if professor is not None:
        professores = [professor] if professor.ativo else []
    else:
        professores = list(
            Professor.objects.filter(ativo=True, tipos_habilitados=tipo_sessao).distinct().order_by("pk")
        )

    equipamentos_fixos = [equipamento] if equipamento is not None else None

    vagas = []
    for prof in professores:
        restantes = limite - len(vagas)
        if restantes <= 0:
            break
        encontradas = _vagas_professor(
            professor=prof,
            tipo_sessao=tipo_sessao,
            dia=dia,
            equipamento_preferido=equipamento,
            equipamentos=equipamentos_fixos,
            hora_desejada=hora_desejada,
            periodo=periodo,
            limite=restantes,
        )
        for encontrada in encontradas:
            vagas.append(
                {
                    "professor": prof,
                    "equipamento": encontrada["equipamento"],
                    "inicio": encontrada["inicio"],
                    "fim": encontrada["fim"],
                }
            )
    return vagas


def resumo_do_dia(dia):
    """Resumo administrativo do dia: contagens gerais, ocupação por
    equipamento e a próxima vaga livre (qualquer professor/equipamento).

    `total_sessoes` e `por_status` consideram TODAS as sessões do dia
    (inclusive canceladas, para mostrar o quanto foi cancelado); as demais
    métricas (`por_professor`, `por_equipamento`, `alunos_distintos`,
    `ocupacao_pct`) consideram só as sessões não canceladas, já que só
    essas de fato ocupam professor/equipamento."""
    inicio_dia = timezone.make_aware(datetime.combine(dia, time.min))
    fim_dia = inicio_dia + timedelta(days=1)

    todas = list(
        Sessao.objects.filter(inicio__gte=inicio_dia, inicio__lt=fim_dia).select_related(
            "professor__usuario", "equipamento", "aluno"
        )
    )
    ativas = [s for s in todas if s.status != Sessao.Status.CANCELADA]

    por_status = {}
    for sessao in todas:
        por_status[sessao.status] = por_status.get(sessao.status, 0) + 1

    por_professor = {}
    for sessao in ativas:
        nome = str(sessao.professor)
        por_professor[nome] = por_professor.get(nome, 0) + 1

    minutos_expediente = expediente.MINUTOS_EXPEDIENTE
    equipamentos_ativos = list(Equipamento.objects.filter(status=Equipamento.Status.ATIVO))
    ids_ativos = [e.pk for e in equipamentos_ativos]

    minutos_reservados_por_equip = {}
    qtd_por_equip = {}
    for sessao in ativas:
        if sessao.equipamento_id is None:
            continue
        minutos = (sessao.reserva_fim - sessao.reserva_inicio).total_seconds() / 60
        minutos_reservados_por_equip[sessao.equipamento_id] = (
            minutos_reservados_por_equip.get(sessao.equipamento_id, 0) + minutos
        )
        qtd_por_equip[sessao.equipamento_id] = qtd_por_equip.get(sessao.equipamento_id, 0) + 1

    minutos_bloqueados_por_equip = {}
    bloqueios = BloqueioEquipamento.objects.filter(
        equipamento_id__in=ids_ativos, inicio__lt=fim_dia, fim__gt=inicio_dia
    )
    for bloqueio in bloqueios:
        sobreposicao = min(bloqueio.fim, fim_dia) - max(bloqueio.inicio, inicio_dia)
        minutos_bloqueados_por_equip[bloqueio.equipamento_id] = minutos_bloqueados_por_equip.get(
            bloqueio.equipamento_id, 0
        ) + max(0, sobreposicao.total_seconds() / 60)

    por_equipamento = {}
    total_reservado = 0.0
    capacidade_total = 0.0
    for equipamento in equipamentos_ativos:
        reservados = minutos_reservados_por_equip.get(equipamento.pk, 0)
        bloqueados = min(minutos_expediente, minutos_bloqueados_por_equip.get(equipamento.pk, 0))
        capacidade_equip = max(0, minutos_expediente - bloqueados)
        pct = round(reservados / capacidade_equip * 100) if capacidade_equip else 0
        por_equipamento[equipamento.nome] = {
            "qtd": qtd_por_equip.get(equipamento.pk, 0),
            "ocupacao_pct": pct,
        }
        total_reservado += reservados
        capacidade_total += capacidade_equip

    ocupacao_pct = round(total_reservado / capacidade_total * 100) if capacidade_total else 0
    alunos_distintos = len({s.aluno_id for s in ativas})

    hoje = timezone.localdate()
    proxima_vaga = None
    if dia >= hoje:
        candidatas = []
        for tipo in TipoSessao.objects.filter(ativo=True):
            encontradas = buscar_vagas(tipo_sessao=tipo, dia=dia, limite=1)
            if encontradas:
                candidatas.append(encontradas[0])
        if candidatas:
            proxima_vaga = min(candidatas, key=lambda vaga: vaga["inicio"])

    return {
        "total_sessoes": len(todas),
        "por_status": por_status,
        "por_professor": por_professor,
        "por_equipamento": por_equipamento,
        "alunos_distintos": alunos_distintos,
        "ocupacao_pct": ocupacao_pct,
        "proxima_vaga": proxima_vaga,
    }


# Limiares (em quantidade de sessões não canceladas no dia) para o nível de
# "movimento" mostrado na faixa de dias (grade) e no calendário de mês. São
# limiares fixos e simples (não derivados da capacidade real de
# equipamentos/professores) — o objetivo é só dar uma noção visual rápida de
# dia parado x dia cheio, não uma métrica exata (essa já existe em
# `resumo_do_dia`, mostrada no cabeçalho do dia selecionado).
NIVEL_BAIXO_MAX = 4
NIVEL_MEDIO_MAX = 9


def nivel_de_movimento(qtd):
    if qtd <= 0:
        return "vazio"
    if qtd <= NIVEL_BAIXO_MAX:
        return "baixo"
    if qtd <= NIVEL_MEDIO_MAX:
        return "medio"
    return "alto"


def contagem_por_dia(inicio, fim):
    """Quantidade de sessões não canceladas por dia, no intervalo [inicio,
    fim] (datas), agrupando pelo horário real (`inicio`) da sessão já
    convertido para o fuso horário de São Paulo — para uma sessão perto da
    meia-noite não "vazar" para o dia UTC errado. Uma única query.
    Devolve {date: qtd}."""
    linhas = (
        Sessao.objects.exclude(status=Sessao.Status.CANCELADA)
        .annotate(dia=TruncDate("inicio", tzinfo=FUSO_SAO_PAULO))
        .filter(dia__gte=inicio, dia__lte=fim)
        .values("dia")
        .annotate(qtd=Count("id"))
        .order_by("dia")
    )
    return {linha["dia"]: linha["qtd"] for linha in linhas}
