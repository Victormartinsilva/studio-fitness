"""
Serviços de agendamento: ações de agendar, remarcar e cancelar uma
sessão, aplicando as regras do motor antes de gravar no banco e
registrando o histórico em EventoSessao.
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from . import motor
from .models import EventoSessao, Sessao


@transaction.atomic
def agendar(*, professor, aluno, tipo, inicio, fim, equipamento=None, contratacao=None, usuario=None):
    if not motor.verificar_disponibilidade(professor, equipamento, inicio, fim, tipo):
        raise ValidationError("Professor ou equipamento indisponível nesse horário.")

    reserva_inicio, reserva_fim, prof_inicio, prof_fim = motor.calcular_janelas(inicio, fim, tipo)

    sessao = Sessao(
        professor=professor,
        aluno=aluno,
        tipo=tipo,
        equipamento=equipamento,
        contratacao=contratacao,
        criado_por=usuario,
        inicio=inicio,
        fim=fim,
        reserva_inicio=reserva_inicio,
        reserva_fim=reserva_fim,
        prof_inicio=prof_inicio,
        prof_fim=prof_fim,
        status=Sessao.Status.AGENDADA,
    )
    sessao.full_clean()
    sessao.save()
    EventoSessao.objects.create(sessao=sessao, usuario=usuario, acao="criada")
    return sessao


@transaction.atomic
def remarcar(*, sessao, inicio, fim, equipamento=None, usuario=None):
    equipamento = equipamento or sessao.equipamento
    if not motor.verificar_disponibilidade(
        sessao.professor, equipamento, inicio, fim, sessao.tipo, excluir_sessao_id=sessao.pk
    ):
        raise ValidationError("Professor ou equipamento indisponível nesse horário.")

    reserva_inicio, reserva_fim, prof_inicio, prof_fim = motor.calcular_janelas(inicio, fim, sessao.tipo)

    sessao.inicio = inicio
    sessao.fim = fim
    sessao.reserva_inicio = reserva_inicio
    sessao.reserva_fim = reserva_fim
    sessao.prof_inicio = prof_inicio
    sessao.prof_fim = prof_fim
    sessao.equipamento = equipamento
    sessao.full_clean()
    sessao.save()
    EventoSessao.objects.create(sessao=sessao, usuario=usuario, acao="remarcada")
    return sessao


@transaction.atomic
def cancelar(*, sessao, justificativa="", usuario=None):
    sessao.status = Sessao.Status.CANCELADA
    sessao.justificativa = justificativa
    sessao.save(update_fields=["status", "justificativa", "atualizado_em"])
    EventoSessao.objects.create(sessao=sessao, usuario=usuario, acao="cancelada", detalhe=justificativa)
    return sessao
