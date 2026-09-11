from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.cadastros.models import Aluno
from apps.contas.permissions import gestor_required

from .forms import AvaliacaoFisicaForm
from .models import AvaliacaoFisica


METRICAS = (
    ("peso_kg", "Peso", "kg", ""),
    ("percentual_gordura", "Gordura corporal", "%", "verde"),
    ("massa_magra_kg", "Massa magra", "kg", "azul"),
)


def _formatar_valor(valor, unidade):
    if valor is None:
        return "—"
    return f"{valor} {unidade}"


def _variacao(atual, anterior, unidade):
    if atual is None or anterior is None:
        return None

    diferenca = atual - anterior
    sinal = "+" if diferenca > 0 else ""
    return f"{sinal}{diferenca} {unidade} desde a anterior"


def _grafico(avaliacoes):
    pontos = [
        (avaliacao.data, avaliacao.peso_kg)
        for avaliacao in reversed(avaliacoes)
        if avaliacao.peso_kg is not None
    ]
    if not pontos:
        return []

    valores = [peso for _, peso in pontos]
    minimo, maximo = min(valores), max(valores)
    amplitude = maximo - minimo
    largura, altura, margem = 340, 120, 20
    divisor = max(len(pontos) - 1, 1)

    grafico = []
    for indice, (data, peso) in enumerate(pontos):
        x = margem + (largura - margem * 2) * indice / divisor
        y = altura / 2 if amplitude == Decimal("0") else (
            altura - margem - float((peso - minimo) / amplitude) * (altura - margem * 2)
        )
        grafico.append(
            {
                "x": round(x, 1),
                "y": round(y, 1),
                "label_y": round(y - 9, 1),
                "peso": peso,
                "data": data.strftime("%d/%m"),
            }
        )
    return grafico


@gestor_required
def evolucao(request, aluno_pk, pk=None):
    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    instancia = get_object_or_404(AvaliacaoFisica, pk=pk, aluno=aluno) if pk else None

    if request.method == "POST" and request.POST.get("_excluir") and instancia:
        instancia.delete()
        messages.success(request, "Avaliação excluída.")
        return redirect("avaliacoes:evolucao", aluno_pk=aluno.pk)

    if request.method == "POST":
        form = AvaliacaoFisicaForm(request.POST, instance=instancia)
        if form.is_valid():
            avaliacao = form.save(commit=False)
            if not avaliacao.registrado_por_id:
                avaliacao.registrado_por = request.user
            avaliacao.aluno = aluno
            avaliacao.save()
            messages.success(request, "Avaliação salva com sucesso.")
            return redirect("avaliacoes:evolucao", aluno_pk=aluno.pk)
    else:
        form = AvaliacaoFisicaForm(instance=instancia)

    avaliacoes = list(
        aluno.avaliacoes.select_related("registrado_por").all()
    )
    atual = avaliacoes[0] if avaliacoes else None
    anterior = avaliacoes[1] if len(avaliacoes) > 1 else None
    metricas = [
        {
            "rotulo": rotulo,
            "valor": _formatar_valor(getattr(atual, campo) if atual else None, unidade),
            "delta": _variacao(
                getattr(atual, campo) if atual else None,
                getattr(anterior, campo) if anterior else None,
                unidade,
            ),
            "classe": classe,
        }
        for campo, rotulo, unidade, classe in METRICAS
    ]

    return render(
        request,
        "avaliacoes/evolucao.html",
        {
            "aluno": aluno,
            "form": form,
            "editando": instancia,
            "avaliacoes": avaliacoes,
            "metricas": metricas,
            "pontos_grafico": _grafico(avaliacoes),
            "aba": "alunos",
            "cancel_arg": aluno.pk,
        },
    )
