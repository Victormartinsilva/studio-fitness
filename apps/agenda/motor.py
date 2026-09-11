"""
Motor de regras da agenda: calcula as janelas de reserva (equipamento) e
de ocupação do professor a partir da sessão real + preparo/troca do
tipo de sessão, e verifica conflitos de horário.
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


def verificar_disponibilidade(professor, equipamento, inicio, fim, tipo_sessao, excluir_sessao_id=None):
    """Retorna True se professor e equipamento estiverem livres no horário pedido."""
    reserva_inicio, reserva_fim, prof_inicio, prof_fim = calcular_janelas(inicio, fim, tipo_sessao)

    return professor_disponivel(
        professor, prof_inicio, prof_fim, excluir_sessao_id
    ) and equipamento_disponivel(equipamento, reserva_inicio, reserva_fim, excluir_sessao_id)
