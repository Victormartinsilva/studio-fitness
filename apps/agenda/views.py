from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Sessao


@login_required
def minhas_sessoes(request):
    usuario = request.user
    sessoes = Sessao.objects.exclude(status=Sessao.Status.CANCELADA)

    if usuario.is_professor and hasattr(usuario, "professor"):
        sessoes = sessoes.filter(professor=usuario.professor)
    elif usuario.is_aluno and hasattr(usuario, "aluno"):
        sessoes = sessoes.filter(aluno=usuario.aluno)

    return render(request, "agenda/minhas_sessoes.html", {"sessoes": sessoes})
