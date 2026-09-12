from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from apps.cadastros.models import Aluno

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


def _num(valor):
    # Formata em string com "." fixo: {{ }} no template localiza Decimal/float
    # para vírgula em pt-br, o que corromperia coordenadas e atributos do SVG.
    return f"{valor:.1f}"


def _grafico(avaliacoes):
    pontos_brutos = [
        (avaliacao.data, avaliacao.peso_kg)
        for avaliacao in reversed(avaliacoes)
        if avaliacao.peso_kg is not None
    ]
    if not pontos_brutos:
        return None

    valores = [peso for _, peso in pontos_brutos]
    minimo, maximo = min(valores), max(valores)
    amplitude = maximo - minimo
    total = len(pontos_brutos)
    indice_maximo = valores.index(maximo)
    indice_minimo = valores.index(minimo)

    largura, altura = 340, 150
    margem_x, topo, base = 22, 24, 30
    plot_altura = altura - topo - base
    baseline_y = altura - base
    divisor = max(total - 1, 1)

    pontos = []
    for indice, (data, peso) in enumerate(pontos_brutos):
        x = margem_x + (largura - margem_x * 2) * indice / divisor
        if amplitude == Decimal("0"):
            y = topo + plot_altura / 2
        else:
            y = topo + plot_altura - float((peso - minimo) / amplitude) * plot_altura
        destaque = total <= 5 or indice in (0, total - 1, indice_maximo, indice_minimo)
        pontos.append(
            {
                "x": _num(x),
                "y": _num(y),
                "label_y": _num(y - 10),
                "peso": str(peso),
                "data": data.strftime("%d/%m"),
                "destaque": destaque,
                "ultimo": indice == total - 1,
                "raio": _num(5 if indice == total - 1 else 3.5),
            }
        )

    baseline_str = _num(baseline_y)
    area = " ".join(f"{ponto['x']},{ponto['y']}" for ponto in pontos)
    area += f" {pontos[-1]['x']},{baseline_str} {pontos[0]['x']},{baseline_str}"

    return {
        "pontos": pontos,
        "area": area,
        "largura": largura,
        "altura": altura,
        "margem_x": margem_x,
        "eixo_x2": largura - margem_x,
        "eixo_y": altura - 6,
        "linhas_grade": [_num(topo), _num(topo + plot_altura / 2), baseline_str],
    }


@login_required
def evolucao(request, aluno_pk, pk=None):
    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    pode_gerenciar = request.user.is_superuser or request.user.is_gestor
    pode_visualizar = pode_gerenciar or (
        request.user.is_aluno
        and hasattr(request.user, "aluno")
        and request.user.aluno.pk == aluno.pk
    )
    if not pode_visualizar:
        raise PermissionDenied("Você não pode acessar as avaliações deste aluno.")

    instancia = get_object_or_404(AvaliacaoFisica, pk=pk, aluno=aluno) if pk else None

    if request.method == "POST" and request.POST.get("_excluir") and instancia:
        if not pode_gerenciar:
            raise PermissionDenied("Você não pode alterar avaliações.")
        instancia.delete()
        messages.success(request, "Avaliação excluída.")
        return redirect("avaliacoes:evolucao", aluno_pk=aluno.pk)

    if request.method == "POST":
        if not pode_gerenciar:
            raise PermissionDenied("Você não pode alterar avaliações.")
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
            "grafico": _grafico(avaliacoes),
            "aba": "alunos",
            "cancel_arg": aluno.pk,
            "pode_gerenciar": pode_gerenciar,
        },
    )
