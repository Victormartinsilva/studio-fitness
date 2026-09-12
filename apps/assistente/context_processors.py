"""
Disponibiliza `assistente_ativo` em todos os templates (mesmo padrão de
`apps.modulos.context_processors.eixos_visiveis`): um booleano espelhando
`settings.ASSISTENTE_ATIVO`, usado por `templates/base.html` para decidir
se mostra o botão flutuante do assistente."""
from django.conf import settings


def assistente_ativo(request):
    return {"assistente_ativo": settings.ASSISTENTE_ATIVO}
