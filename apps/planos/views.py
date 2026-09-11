from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.contas.permissions import gestor_required

from .forms import ContratacaoForm, PlanoForm
from .models import Contratacao, Plano


@gestor_required
def planos(request, pk=None):
    instancia = get_object_or_404(Plano, pk=pk) if pk else None

    if request.method == "POST" and request.POST.get("_excluir") and instancia:
        instancia.delete()
        messages.success(request, "Plano excluído.")
        return redirect("planos:planos")

    if request.method == "POST":
        form = PlanoForm(request.POST, instance=instancia)
        if form.is_valid():
            form.save()
            messages.success(request, "Plano salvo com sucesso.")
            return redirect("planos:planos")
    else:
        form = PlanoForm(instance=instancia)

    itens = Plano.objects.all()
    return render(request, "planos/planos.html", {"form": form, "itens": itens, "editando": instancia})


@gestor_required
def contratacoes(request, pk=None):
    instancia = get_object_or_404(Contratacao, pk=pk) if pk else None

    if request.method == "POST" and request.POST.get("_excluir") and instancia:
        instancia.delete()
        messages.success(request, "Contratação excluída.")
        return redirect("planos:contratacoes")

    if request.method == "POST":
        form = ContratacaoForm(request.POST, instance=instancia)
        if form.is_valid():
            form.save()
            messages.success(request, "Contratação salva com sucesso.")
            return redirect("planos:contratacoes")
    else:
        form = ContratacaoForm(instance=instancia)

    itens = Contratacao.objects.select_related("aluno", "plano").all()
    return render(
        request, "planos/contratacoes.html", {"form": form, "itens": itens, "editando": instancia}
    )
