from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.contas.permissions import gestor_required

from . import servicos
from .forms import CobrancaForm
from .models import Cobranca


@gestor_required
def cobrancas(request, pk=None):
    instancia = get_object_or_404(Cobranca, pk=pk) if pk else None

    if request.method == "POST" and request.POST.get("_excluir") and instancia:
        instancia.delete()
        messages.success(request, "Cobrança excluída.")
        return redirect("financeiro:cobrancas")

    if request.method == "POST" and request.POST.get("_pagar") and instancia:
        try:
            servicos.registrar_pagamento(cobranca=instancia, usuario=request.user)
            messages.success(request, "Cobrança marcada como paga.")
        except ValidationError as erro:
            messages.error(request, erro.message)
        return redirect("financeiro:cobrancas")

    if request.method == "POST" and request.POST.get("_cancelar") and instancia:
        try:
            servicos.cancelar_cobranca(cobranca=instancia, usuario=request.user)
            messages.success(request, "Cobrança cancelada.")
        except ValidationError as erro:
            messages.error(request, erro.message)
        return redirect("financeiro:cobrancas")

    if request.method == "POST":
        form = CobrancaForm(request.POST, instance=instancia)
        if form.is_valid():
            form.save()
            messages.success(request, "Cobrança salva com sucesso.")
            return redirect("financeiro:cobrancas")
    else:
        form = CobrancaForm(instance=instancia)

    itens = Cobranca.objects.select_related("contratacao__aluno", "contratacao__plano")

    status = request.GET.get("status", "")
    hoje = timezone.localdate()
    if status == "pendente":
        itens = itens.filter(status=Cobranca.Status.PENDENTE, vencimento__gte=hoje)
    elif status == "atrasada":
        itens = itens.filter(status=Cobranca.Status.PENDENTE, vencimento__lt=hoje)
    elif status == "paga":
        itens = itens.filter(status=Cobranca.Status.PAGA)
    elif status == "cancelada":
        itens = itens.filter(status=Cobranca.Status.CANCELADA)

    return render(
        request,
        "financeiro/cobrancas.html",
        {"form": form, "itens": itens, "editando": instancia, "aba": "financeiro", "status": status},
    )


@gestor_required
def gerar(request):
    if request.method == "POST":
        criadas = servicos.gerar_cobrancas(usuario=request.user)
        if criadas:
            messages.success(request, f"{len(criadas)} cobrança(s) gerada(s).")
        else:
            messages.info(request, "Nenhuma cobrança nova para gerar — tudo em dia.")
    return redirect("financeiro:cobrancas")
