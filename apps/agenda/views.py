from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from . import motor, servicos
from .forms import AgendarForm
from .models import Sessao


@login_required
def minhas_sessoes(request):
    usuario = request.user
    sessoes = Sessao.objects.exclude(status=Sessao.Status.CANCELADA)

    if usuario.is_professor and hasattr(usuario, "professor"):
        sessoes = sessoes.filter(professor=usuario.professor)
    elif usuario.is_aluno and hasattr(usuario, "aluno"):
        sessoes = sessoes.filter(aluno=usuario.aluno)

    pode_agendar = usuario.is_superuser or usuario.is_gestor or usuario.is_professor
    return render(
        request,
        "agenda/minhas_sessoes.html",
        {
            "sessoes": sessoes.select_related("professor__usuario", "aluno", "equipamento"),
            "pode_agendar": pode_agendar,
            "aba": "agenda",
        },
    )


@login_required
def agendar(request):
    if not (request.user.is_superuser or request.user.is_gestor or request.user.is_professor):
        raise PermissionDenied("Você não pode criar sessões.")

    sugestoes = []

    if request.method == "POST":
        form = AgendarForm(request.POST)
        if form.is_valid():
            dados = form.cleaned_data
            inicio = timezone.make_aware(datetime.combine(dados["data"], dados["hora_inicio"]))
            fim = inicio + timedelta(minutes=dados["tipo"].duracao_min)
            try:
                servicos.agendar(
                    professor=dados["professor"],
                    aluno=dados["aluno"],
                    tipo=dados["tipo"],
                    equipamento=dados["equipamento"],
                    inicio=inicio,
                    fim=fim,
                    usuario=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, exc.message)
                sugestoes = _sugestoes_para_template(
                    professor=dados["professor"],
                    tipo=dados["tipo"],
                    dia=dados["data"],
                    hora_desejada=dados["hora_inicio"],
                    equipamento_preferido=dados["equipamento"],
                    aluno=dados["aluno"],
                )
            else:
                messages.success(request, "Sessão agendada com sucesso.")
                return redirect("agenda:minhas_sessoes")
    else:
        form = AgendarForm(
            initial={
                "data": request.GET.get("data"),
                "hora_inicio": request.GET.get("hora_inicio"),
                "equipamento": request.GET.get("equipamento"),
                "professor": request.GET.get("professor"),
                "tipo": request.GET.get("tipo"),
                "aluno": request.GET.get("aluno"),
            }
        )

    return render(request, "agenda/agendar.html", {"form": form, "aba": "agenda", "sugestoes": sugestoes})


def _sugestoes_para_template(*, professor, tipo, dia, hora_desejada, equipamento_preferido, aluno):
    """Monta os links de "agenda inteligente": horários/equipamentos livres
    para o mesmo professor e tipo de sessão, prontos para reabrir o
    formulário já preenchido."""
    encontradas = motor.sugerir_horarios(
        professor=professor,
        tipo_sessao=tipo,
        dia=dia,
        equipamento_preferido=equipamento_preferido,
        hora_desejada=hora_desejada,
    )
    base = reverse("agenda:agendar")
    sugestoes = []
    for opcao in encontradas:
        inicio_local = timezone.localtime(opcao["inicio"])
        sugestoes.append(
            {
                "equipamento": opcao["equipamento"],
                "inicio": inicio_local,
                "fim": timezone.localtime(opcao["fim"]),
                "href": (
                    f"{base}?data={dia.isoformat()}&hora_inicio={inicio_local:%H:%M}"
                    f"&equipamento={opcao['equipamento'].id}&professor={professor.id}"
                    f"&tipo={tipo.id}&aluno={aluno.id}"
                ),
            }
        )
    return sugestoes


@login_required
def cancelar(request, pk):
    sessao = get_object_or_404(Sessao, pk=pk)
    usuario = request.user
    pode_cancelar = (
        usuario.is_superuser
        or usuario.is_gestor
        or (usuario.is_professor and hasattr(usuario, "professor") and sessao.professor_id == usuario.professor.id)
    )
    if not pode_cancelar:
        raise PermissionDenied("Você não pode cancelar esta sessão.")

    if request.method == "POST":
        servicos.cancelar(sessao=sessao, usuario=usuario)
        messages.success(request, "Sessão cancelada.")
    return redirect("agenda:minhas_sessoes")

