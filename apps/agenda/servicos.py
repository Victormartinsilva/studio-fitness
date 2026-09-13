"""
Serviços de agendamento: ações de agendar, remarcar e cancelar uma
sessão, aplicando as regras do motor antes de gravar no banco e
registrando o histórico em EventoSessao.
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.cadastros.models import Equipamento, Professor
from apps.planos.models import Contratacao

from . import motor
from .models import EventoSessao, Sessao


@transaction.atomic
def agendar(
    *, professor, aluno, tipo, inicio, fim, equipamento=None, contratacao=None, usuario=None, detalhe=""
):
    # Lock nas linhas de professor/equipamento durante toda a checagem +
    # gravação, para não deixar duas requisições concorrentes passarem pela
    # checagem de disponibilidade e só depois colidirem na gravação.
    professor = Professor.objects.select_for_update().get(pk=professor.pk)
    if equipamento is not None:
        equipamento = Equipamento.objects.select_for_update().get(pk=equipamento.pk)

    motivo = motor.motivo_indisponibilidade(professor, equipamento, inicio, fim, tipo, aluno=aluno)
    if motivo:
        raise ValidationError(motivo)

    if contratacao is None:
        contratacao = (
            Contratacao.objects.filter(aluno=aluno, status=Contratacao.Status.ATIVA)
            .order_by("-criado_em")
            .first()
        )

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
    EventoSessao.objects.create(sessao=sessao, usuario=usuario, acao="criada", detalhe=detalhe)
    return sessao


@transaction.atomic
def remarcar(*, sessao, inicio, fim, equipamento=None, usuario=None):
    equipamento = equipamento or sessao.equipamento

    professor = Professor.objects.select_for_update().get(pk=sessao.professor_id)
    if equipamento is not None:
        equipamento = Equipamento.objects.select_for_update().get(pk=equipamento.pk)

    motivo = motor.motivo_indisponibilidade(
        professor, equipamento, inicio, fim, sessao.tipo, aluno=sessao.aluno, excluir_sessao_id=sessao.pk
    )
    if motivo:
        raise ValidationError(motivo)

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
def marcar_status(*, sessao, status, usuario=None, detalhe=""):
    """Muda o status da sessão (ex.: confirmada/realizada/faltou) e registra
    o evento correspondente. Simples "setter com auditoria": não valida
    transições de estado (ex. não impede ir de "cancelada" para
    "realizada") — a única checagem é que `status` seja um valor válido de
    `Sessao.Status`. Quem chama (a view) já cuida da permissão."""
    valores_validos = {valor for valor, _ in Sessao.Status.choices}
    if status not in valores_validos:
        raise ValidationError(f'Status inválido: "{status}".')

    sessao.status = status
    sessao.save(update_fields=["status", "atualizado_em"])
    EventoSessao.objects.create(sessao=sessao, usuario=usuario, acao=f"status:{status}", detalhe=detalhe)
    return sessao


@transaction.atomic
def cancelar(*, sessao, justificativa="", usuario=None, detalhe=""):
    sessao.status = Sessao.Status.CANCELADA
    sessao.justificativa = justificativa
    sessao.save(update_fields=["status", "justificativa", "atualizado_em"])
    # `detalhe` é um complemento opcional pro registro do evento (ex.: "via
    # assistente"); sem ele, mantém o comportamento antigo de registrar a
    # própria justificativa como detalhe do evento.
    EventoSessao.objects.create(
        sessao=sessao, usuario=usuario, acao="cancelada", detalhe=detalhe or justificativa
    )
    return sessao
