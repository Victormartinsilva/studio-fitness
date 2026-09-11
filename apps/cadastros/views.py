from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.contas.permissions import gestor_required, professor_required

from .forms import AlunoForm, EquipamentoForm, TipoSessaoForm
from .models import Aluno, Equipamento, TipoSessao


def _crud_simples(request, model, form_class, template, url_name, aba, pk=None):
    """Lida com list+create+update+delete de um cadastro simples (mesmo padrão para os 3)."""
    instancia = get_object_or_404(model, pk=pk) if pk else None

    if request.method == "POST" and request.POST.get("_excluir") and instancia:
        instancia.delete()
        messages.success(request, "Registro excluído.")
        return redirect(url_name)

    if request.method == "POST":
        form = form_class(request.POST, instance=instancia)
        if form.is_valid():
            form.save()
            messages.success(request, "Salvo com sucesso.")
            return redirect(url_name)
    else:
        form = form_class(instance=instancia)

    itens = model.objects.all()
    return render(request, template, {"form": form, "itens": itens, "editando": instancia, "aba": aba})


@gestor_required
def alunos(request, pk=None):
    return _crud_simples(request, Aluno, AlunoForm, "cadastros/alunos.html", "cadastros:alunos", "alunos", pk)


@gestor_required
def equipamentos(request, pk=None):
    return _crud_simples(
        request, Equipamento, EquipamentoForm, "cadastros/equipamentos.html", "cadastros:equipamentos",
        "equipamentos", pk,
    )


@gestor_required
def tipos_sessao(request, pk=None):
    return _crud_simples(
        request, TipoSessao, TipoSessaoForm, "cadastros/tipos_sessao.html", "cadastros:tipos_sessao",
        "tipos", pk,
    )


@professor_required
def meus_alunos(request):
    """Lista os alunos com quem o professor logado tem sessões agendadas
    (passadas ou futuras, exceto canceladas), com um resumo de frequência."""
    from apps.agenda.models import Sessao  # import tardio evita ciclo entre apps

    professor = request.user.professor
    agora = timezone.now()
    sessoes = (
        Sessao.objects.filter(professor=professor)
        .exclude(status=Sessao.Status.CANCELADA)
        .select_related("aluno")
        .order_by("inicio")
    )

    resumo = {}
    for sessao in sessoes:
        info = resumo.setdefault(
            sessao.aluno_id, {"aluno": sessao.aluno, "total": 0, "proxima": None, "ultima": None}
        )
        info["total"] += 1
        if sessao.inicio >= agora and (info["proxima"] is None or sessao.inicio < info["proxima"]):
            info["proxima"] = sessao.inicio
        if sessao.inicio < agora and (info["ultima"] is None or sessao.inicio > info["ultima"]):
            info["ultima"] = sessao.inicio

    itens = sorted(resumo.values(), key=lambda item: item["aluno"].nome)
    return render(request, "cadastros/meus_alunos.html", {"itens": itens, "aba": "meus_alunos"})
