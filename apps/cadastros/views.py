from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.contas.permissions import gestor_required

from .forms import AlunoForm, EquipamentoForm, TipoSessaoForm
from .models import Aluno, Equipamento, TipoSessao


def _crud_simples(request, model, form_class, template, url_name, pk=None):
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
    return render(request, template, {"form": form, "itens": itens, "editando": instancia})


@gestor_required
def alunos(request, pk=None):
    return _crud_simples(request, Aluno, AlunoForm, "cadastros/alunos.html", "cadastros:alunos", pk)


@gestor_required
def equipamentos(request, pk=None):
    return _crud_simples(
        request, Equipamento, EquipamentoForm, "cadastros/equipamentos.html", "cadastros:equipamentos", pk
    )


@gestor_required
def tipos_sessao(request, pk=None):
    return _crud_simples(
        request, TipoSessao, TipoSessaoForm, "cadastros/tipos_sessao.html", "cadastros:tipos_sessao", pk
    )
