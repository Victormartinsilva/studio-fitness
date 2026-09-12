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

    return alertas
