from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.cadastros.models import Aluno
from apps.modulos.models import eixo_visivel

from . import evolucao as ev
from .forms import AvaliacaoFisicaForm
from .models import AvaliacaoFisica


def _pode_gerenciar(usuario):
    return usuario.is_superuser or usuario.is_gestor


def _aluno_do_usuario(usuario):
    return getattr(usuario, "aluno", None) if usuario.is_aluno else None


def _evolucao_visivel_para(usuario):
    """Eixo "Minha evolução" (Pacote Plus): visível por padrão para o aluno,
    mas o administrador pode escondê-lo em /modulos/visoes/."""
    return eixo_visivel(usuario, "evolucao")


def _aluno_visivel(request, aluno_pk):
    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    proprio = _aluno_do_usuario(request.user)
    if _pode_gerenciar(request.user):
        return aluno
    if not (proprio and proprio.pk == aluno.pk):
        raise PermissionDenied("Você não pode acessar as avaliações deste aluno.")
    if not _evolucao_visivel_para(request.user):
        raise Http404("Página não disponível.")
    return aluno


def _avaliacoes(aluno):
    return list(aluno.avaliacoes.select_related("registrado_por").all())


@login_required
def minha_evolucao(request):
    if not request.user.is_aluno:
        return redirect("painel:home")
    if not _evolucao_visivel_para(request.user):
        raise Http404("Página não disponível.")

    aluno = _aluno_do_usuario(request.user)
    avaliacoes = _avaliacoes(aluno) if aluno else []
    return render(
        request,
        "avaliacoes/minha_evolucao.html",
        {
            "aba": "evolucao",
            "aluno": aluno,
            "url_base": reverse("avaliacoes:minha_evolucao"),
            "url_comparar": reverse("avaliacoes:minha_comparacao"),
            "pode_compartilhar": True,
            **ev.contexto_painel(avaliacoes, request.GET.get("metrica")),
        },
    )


@login_required
def comparar(request, aluno_pk=None):
    if aluno_pk is None:
        if not request.user.is_aluno or not _evolucao_visivel_para(request.user):
            raise Http404("Página não disponível.")
        aluno = _aluno_do_usuario(request.user)
        if aluno is None:
            return redirect("avaliacoes:minha_evolucao")
        url_voltar = reverse("avaliacoes:minha_evolucao")
        aba = "evolucao"
    else:
        aluno = _aluno_visivel(request, aluno_pk)
        url_voltar = reverse("avaliacoes:evolucao", args=[aluno.pk])
        aba = "alunos"

    avaliacoes = _avaliacoes(aluno)
    if len(avaliacoes) < 2:
        return redirect(url_voltar)

    por_id = {str(a.pk): a for a in avaliacoes}
    de = por_id.get(request.GET.get("de"), avaliacoes[-1])
    ate = por_id.get(request.GET.get("ate"), avaliacoes[0])
    if (de.data, de.pk) > (ate.data, ate.pk):
        de, ate = ate, de
    indicadores = ev.indicadores_comparacao(de, ate)

    return render(
        request,
        "avaliacoes/comparar.html",
        {
            "aba": aba,
            "aluno": aluno,
            "avaliacoes": avaliacoes,
            "de": de,
            "ate": ate,
            "linhas": [indicadores[campo] for campo in ev.METRICAS],
            "medidas": {c.replace("_cm", ""): indicadores[c] for c in ev.MEDIDAS},
            "url_voltar": url_voltar,
        },
    )


@login_required
def evolucao(request, aluno_pk, pk=None):
    aluno = _aluno_visivel(request, aluno_pk)
    pode_gerenciar = _pode_gerenciar(request.user)
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

    return render(
        request,
        "avaliacoes/evolucao.html",
        {
            "aluno": aluno,
            "form": form,
            "editando": instancia,
            "aba": "alunos",
            "cancel_arg": aluno.pk,
            "pode_gerenciar": pode_gerenciar,
            "url_base": reverse("avaliacoes:evolucao", args=[aluno.pk]),
            "url_comparar": reverse("avaliacoes:comparar", args=[aluno.pk]),
            "pode_compartilhar": False,
            **ev.contexto_painel(_avaliacoes(aluno), request.GET.get("metrica")),
        },
    )
