"""
Motor de regras da agenda: calcula as janelas de reserva (equipamento) e
de ocupação do professor a partir da sessão real + preparo/troca do
tipo de sessão, e verifica se o horário pedido é possível — professor
habilitado ao tipo de sessão, dentro da disponibilidade cadastrada,
sem conflito de horário, e equipamento ativo e livre.
"""
from datetime import datetime, time, timedelta

from django.utils import timezone

from apps.cadastros.models import Equipamento

from .models import Sessao


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
    sessoes = Sessao.objects.filter(professor=professor).exclude(status=Sessao.Status.CANCELADA)
    if excluir_sessao_id:
        sessoes = sessoes.exclude(pk=excluir_sessao_id)

    for sessao in sessoes:
        if _periodos_se_sobrepoem(prof_inicio, prof_fim, sessao.prof_inicio, sessao.prof_fim):
            return False
    return True


def equipamento_disponivel(equipamento, reserva_inicio, reserva_fim, excluir_sessao_id=None):
    if equipamento is None:
        return True

    sessoes = Sessao.objects.filter(equipamento=equipamento).exclude(status=Sessao.Status.CANCELADA)
    if excluir_sessao_id:
        sessoes = sessoes.exclude(pk=excluir_sessao_id)

    for sessao in sessoes:
        if _periodos_se_sobrepoem(reserva_inicio, reserva_fim, sessao.reserva_inicio, sessao.reserva_fim):
            return False

    for bloqueio in equipamento.bloqueios.all():
        if _periodos_se_sobrepoem(reserva_inicio, reserva_fim, bloqueio.inicio, bloqueio.fim):
            return False
    return True


def motivo_indisponibilidade(professor, equipamento, inicio, fim, tipo_sessao, excluir_sessao_id=None):
    """Retorna uma mensagem explicando por que o horário não pode ser confirmado,
    ou None se professor e equipamento estiverem livres e aptos."""
    if not professor_habilitado(professor, tipo_sessao):
        return f'{professor} não está habilitado para o tipo de sessão "{tipo_sessao}".'

    reserva_inicio, reserva_fim, prof_inicio, prof_fim = calcular_janelas(inicio, fim, tipo_sessao)

    if not professor_dentro_da_disponibilidade(professor, prof_inicio, prof_fim):
        return f"{professor} não tem disponibilidade cadastrada nesse horário."

    if not professor_disponivel(professor, prof_inicio, prof_fim, excluir_sessao_id):
        return f"{professor} já tem outra sessão nesse horário."

    if not equipamento_ativo(equipamento):
        return f"{equipamento} está {equipamento.get_status_display().lower()} e não pode ser reservado."

    if not equipamento_disponivel(equipamento, reserva_inicio, reserva_fim, excluir_sessao_id):
        return f"{equipamento} já está reservado ou bloqueado nesse horário."

    return None


def verificar_disponibilidade(professor, equipamento, inicio, fim, tipo_sessao, excluir_sessao_id=None):
    """Retorna True se professor e equipamento estiverem livres e aptos no horário pedido."""
    return (
        motivo_indisponibilidade(professor, equipamento, inicio, fim, tipo_sessao, excluir_sessao_id)
        is None
    )


ABERTURA_PADRAO = time(7, 0)
FECHAMENTO_PADRAO = time(21, 0)
PASSO_SUGESTAO_MIN = 30
LIMITE_SUGESTOES = 6


def sugerir_horarios(
    *,
    professor,
    tipo_sessao,
    dia,
    equipamento_preferido=None,
    hora_desejada=None,
    abertura=ABERTURA_PADRAO,
    fechamento=FECHAMENTO_PADRAO,
    passo_min=PASSO_SUGESTAO_MIN,
    limite=LIMITE_SUGESTOES,
):
    """Agenda inteligente: varre o expediente do dia e devolve até `limite`
    combinações (equipamento, início, fim) livres para o professor e tipo de
    sessão pedidos — no máximo uma por equipamento, priorizando o equipamento
    preferido e o horário mais próximo do desejado. Devolve lista vazia se o
    professor não estiver habilitado para o tipo de sessão.

    Para não repetir consultas ao banco a cada combinação de horário ×
    equipamento, as sessões/disponibilidades do professor e as
    sessões/bloqueios de cada equipamento são carregados uma única vez e as
    sobreposições são checadas em memória."""
    if not professor_habilitado(professor, tipo_sessao):
        return []

    duracao = timedelta(minutes=tipo_sessao.duracao_min)
    inicio_expediente = timezone.make_aware(datetime.combine(dia, abertura))
    fim_expediente = timezone.make_aware(datetime.combine(dia, fechamento))
    agora = timezone.now()
    passo = timedelta(minutes=passo_min)
    alvo = timezone.make_aware(datetime.combine(dia, hora_desejada)) if hora_desejada else max(inicio_expediente, agora)

    momentos = []
    momento = inicio_expediente
    while momento + duracao <= fim_expediente:
        if momento >= agora:
            momentos.append(momento)
        momento += passo
    momentos.sort(key=lambda m: (abs((m - alvo).total_seconds()), m))

    equipamentos = list(Equipamento.objects.filter(status=Equipamento.Status.ATIVO).order_by("nome"))
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
