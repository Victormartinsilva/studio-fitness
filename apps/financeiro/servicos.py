"""
Serviços financeiros: geração de cobranças e as ações que mudam o status
de uma cobrança (dar baixa/cancelar) — únicos pontos que devem mutar
`Cobranca`, sempre registrando um `EventoCobranca` (mesmo padrão de
`apps/agenda/servicos.py`).
"""
import calendar
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.planos.models import Contratacao, Plano

from .models import Cobranca, EventoCobranca


def _vencimento_recorrente(contratacao, ano, mes):
    # Mantém o "dia do mês" da data de início da contratação, recuando pro
    # último dia do mês quando ele não existe (ex.: contratação iniciada no
    # dia 31 cobrando em fevereiro).
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    dia = min(contratacao.data_inicio.day, ultimo_dia)
    return date(ano, mes, dia)


@transaction.atomic
def gerar_cobrancas(*, referencia=None, usuario=None):
    """Cria as cobranças em aberto do mês de `referencia` (padrão: hoje).
    Idempotente — rodar de novo no mesmo mês não duplica o que já foi
    gerado — pensado pra ser disparado sob demanda pelo gestor (etapa
    decidiu não ter geração automática/cron nesta fase).

    - Recorrente: 1 cobrança por competência (mês/ano), enquanto a
      contratação estiver ativa.
    - Pacote: 1 cobrança única, na vida inteira da contratação.
    """
    referencia = referencia or timezone.localdate()
    competencia = f"{referencia.month:02d}/{referencia.year}"
    ativas = Contratacao.objects.filter(status=Contratacao.Status.ATIVA).select_related("plano", "aluno")

    criadas = []

    for contratacao in ativas.filter(plano__modalidade=Plano.Modalidade.RECORRENTE):
        if Cobranca.objects.filter(contratacao=contratacao, competencia=competencia).exists():
            continue
        cobranca = Cobranca.objects.create(
            contratacao=contratacao,
            competencia=competencia,
            valor=contratacao.plano.valor or 0,
            vencimento=_vencimento_recorrente(contratacao, referencia.year, referencia.month),
        )
        EventoCobranca.objects.create(cobranca=cobranca, usuario=usuario, acao="gerada")
        criadas.append(cobranca)

    for contratacao in ativas.filter(plano__modalidade=Plano.Modalidade.PACOTE):
        if Cobranca.objects.filter(contratacao=contratacao).exists():
            continue
        cobranca = Cobranca.objects.create(
            contratacao=contratacao,
            competencia="Pacote",
            valor=contratacao.plano.valor or 0,
            vencimento=contratacao.data_inicio,
        )
        EventoCobranca.objects.create(cobranca=cobranca, usuario=usuario, acao="gerada")
        criadas.append(cobranca)

    return criadas


@transaction.atomic
def registrar_pagamento(*, cobranca, data_pagamento=None, usuario=None):
    if cobranca.status != Cobranca.Status.PENDENTE:
        raise ValidationError("Só é possível dar baixa em uma cobrança pendente.")

    cobranca.status = Cobranca.Status.PAGA
    cobranca.data_pagamento = data_pagamento or timezone.localdate()
    cobranca.save(update_fields=["status", "data_pagamento"])
    EventoCobranca.objects.create(cobranca=cobranca, usuario=usuario, acao="paga")
    return cobranca


@transaction.atomic
def cancelar_cobranca(*, cobranca, usuario=None, motivo=""):
    if cobranca.status != Cobranca.Status.PENDENTE:
        raise ValidationError("Só é possível cancelar uma cobrança pendente.")

    cobranca.status = Cobranca.Status.CANCELADA
    cobranca.save(update_fields=["status"])
    EventoCobranca.objects.create(cobranca=cobranca, usuario=usuario, acao="cancelada", detalhe=motivo)
    return cobranca
