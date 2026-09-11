"""
Motor de regras da agenda: calcula as janelas de reserva (equipamento) e
de ocupação do professor a partir da sessão real + preparo/troca do
tipo de sessão, e verifica se o horário pedido é possível — professor
habilitado ao tipo de sessão, dentro da disponibilidade cadastrada,
sem conflito de horário, e equipamento ativo e livre.
"""
from datetime import timedelta

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
