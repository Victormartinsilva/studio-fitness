"""
Regras para os alertas exibidos na home: sessões nas próximas horas.
"""
from datetime import timedelta

from django.utils import timezone

from apps.agenda.models import Sessao


def gerar_alertas(usuario):
    """Retorna uma lista de alertas (dict com 'nivel' e 'mensagem') relevantes para o usuário."""
    alertas = []
    agora = timezone.now()
    daqui_a_pouco = agora + timedelta(hours=24)

    sessoes = (
        Sessao.objects.filter(inicio__gte=agora, inicio__lte=daqui_a_pouco)
        .exclude(status=Sessao.Status.CANCELADA)
        .select_related("aluno", "professor__usuario")
    )

    if usuario.is_professor and hasattr(usuario, "professor"):
        sessoes = sessoes.filter(professor=usuario.professor)
    elif usuario.is_aluno and hasattr(usuario, "aluno"):
        sessoes = sessoes.filter(aluno=usuario.aluno)

    for sessao in sessoes.order_by("inicio"):
        if usuario.is_professor:
            mensagem = f"Sessão com {sessao.aluno} em {sessao.inicio:%d/%m %H:%M}."
        else:
            mensagem = f"Sessão com {sessao.professor} em {sessao.inicio:%d/%m %H:%M}."
        alertas.append({"nivel": "info", "mensagem": mensagem})

    if usuario.is_superuser or usuario.is_gestor:
        alertas.extend(_alertas_financeiro())

    return alertas


def _alertas_financeiro():
    """Cobranças atrasadas (crítico) e a vencer nos próximos 2 dias (aviso).
    Import tardio evita import de `apps.financeiro` em todo carregamento de
    página pra quem nunca vê esses alertas (professor/aluno)."""
    from apps.financeiro.models import Cobranca

    alertas = []
    hoje = timezone.localdate()

    atrasadas = Cobranca.objects.filter(status=Cobranca.Status.PENDENTE, vencimento__lt=hoje)
    total_atrasadas = atrasadas.count()
    if total_atrasadas:
        alertas.append(
            {
                "nivel": "critico",
                "mensagem": f"{total_atrasadas} cobrança(s) atrasada(s).",
                "detalhe": "Veja em Financeiro.",
            }
        )

    a_vencer = (
        Cobranca.objects.filter(
            status=Cobranca.Status.PENDENTE, vencimento__gte=hoje, vencimento__lte=hoje + timedelta(days=2)
        )
        .select_related("contratacao__aluno")
        .order_by("vencimento")
    )
    for cobranca in a_vencer:
        alertas.append(
            {
                "nivel": "aviso",
                "mensagem": f"Cobrança de {cobranca.contratacao.aluno} vence em {cobranca.vencimento:%d/%m}.",
            }
        )

    return alertas
