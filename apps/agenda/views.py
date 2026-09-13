from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.cadastros.models import Aluno

from . import motor, servicos
from .forms import AgendarForm, RemararForm
from .models import Sessao
from .permissoes import _digitos, _pode_gerenciar_sessao


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
        professor_inicial = request.GET.get("professor")
        if not professor_inicial and request.user.is_professor and hasattr(request.user, "professor"):
            # Formulário aberto "em branco" (FAB/"+ Agendar sessão", sem vaga
            # clicada): pré-seleciona o próprio professor logado. Um
            # `professor=` explícito na URL (vaga clicada na grade, possivelmente
            # de outro professor) sempre tem prioridade sobre isso.
            professor_inicial = request.user.professor.id

        form = AgendarForm(
            initial={
                "data": request.GET.get("data"),
                "hora_inicio": request.GET.get("hora_inicio"),
                "equipamento": request.GET.get("equipamento"),
                "professor": professor_inicial,
                "tipo": request.GET.get("tipo"),
                "aluno": request.GET.get("aluno"),
            }
        )

    alunos_ativos = Aluno.objects.filter(ativo=True).order_by("nome")
    return render(
        request,
        "agenda/agendar.html",
        {"form": form, "aba": "agenda", "sugestoes": sugestoes, "alunos_ativos": alunos_ativos},
    )


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
    if not _pode_gerenciar_sessao(usuario, sessao):
        raise PermissionDenied("Você não pode cancelar esta sessão.")

    if request.method == "POST":
        justificativa = request.POST.get("justificativa", "")
        servicos.cancelar(sessao=sessao, justificativa=justificativa, usuario=usuario)
        messages.success(request, "Sessão cancelada.")
    return redirect("agenda:minhas_sessoes")


@login_required
def detalhe(request, pk):
    sessao = get_object_or_404(
        Sessao.objects.select_related("aluno", "professor__usuario", "tipo", "equipamento"), pk=pk
    )
    usuario = request.user

    # Privacidade (LGPD): mesma regra já aplicada na grade — um aluno só
    # pode ver o detalhe completo da PRÓPRIA sessão. Professor (qualquer
    # um, não só o dono) e gestor/superuser podem ver o detalhe de
    # qualquer sessão; só os botões de ação ficam restritos ao dono
    # (`_pode_gerenciar_sessao`, checado abaixo para `pode_gerenciar`).
    eh_aluno_dono = (
        usuario.is_aluno and hasattr(usuario, "aluno") and sessao.aluno_id == usuario.aluno.id
    )
    pode_ver = usuario.is_superuser or usuario.is_gestor or usuario.is_professor or eh_aluno_dono
    if not pode_ver:
        raise PermissionDenied("Você não pode ver esta sessão.")

    pode_gerenciar = _pode_gerenciar_sessao(usuario, sessao)

    link_whatsapp = None
    if pode_gerenciar:
        digitos = _digitos(sessao.aluno.telefone)
        if digitos:
            link_whatsapp = f"https://wa.me/55{digitos}"

    return render(
        request,
        "agenda/detalhe.html",
        {
            "sessao": sessao,
            "pode_gerenciar": pode_gerenciar,
            "link_whatsapp": link_whatsapp,
            "aba": "agenda",
        },
    )


@login_required
@require_POST
def status(request, pk):
    sessao = get_object_or_404(Sessao, pk=pk)
    usuario = request.user
    if not _pode_gerenciar_sessao(usuario, sessao):
        raise PermissionDenied("Você não pode mudar o status desta sessão.")

    valor = request.POST.get("status")
    valores_permitidos = {Sessao.Status.CONFIRMADA, Sessao.Status.REALIZADA, Sessao.Status.FALTOU}
    if valor not in valores_permitidos:
        messages.error(request, "Status inválido.")
        return redirect("agenda:detalhe", pk=sessao.pk)

    try:
        servicos.marcar_status(sessao=sessao, status=valor, usuario=usuario)
    except ValidationError as exc:
        messages.error(request, exc.message)
    else:
        messages.success(request, f"Sessão marcada como {sessao.get_status_display().lower()}.")
    return redirect("agenda:detalhe", pk=sessao.pk)


@login_required
def remarcar(request, pk):
    sessao = get_object_or_404(Sessao, pk=pk)
    usuario = request.user
    if not _pode_gerenciar_sessao(usuario, sessao):
        raise PermissionDenied("Você não pode remarcar esta sessão.")

    if request.method == "POST":
        form = RemararForm(request.POST)
        if form.is_valid():
            dados = form.cleaned_data
            inicio = timezone.make_aware(datetime.combine(dados["data"], dados["hora_inicio"]))
            fim = inicio + timedelta(minutes=sessao.tipo.duracao_min)
            try:
                servicos.remarcar(
                    sessao=sessao, inicio=inicio, fim=fim, equipamento=dados["equipamento"], usuario=usuario
                )
            except ValidationError as exc:
                form.add_error(None, exc.message)
            else:
                messages.success(request, "Sessão remarcada com sucesso.")
                return redirect("agenda:detalhe", pk=sessao.pk)
    else:
        inicio_local = timezone.localtime(sessao.inicio)
        form = RemararForm(
            initial={
                "data": inicio_local.date(),
                "hora_inicio": inicio_local.time(),
                "equipamento": sessao.equipamento_id,
            }
        )

    return render(request, "agenda/remarcar.html", {"form": form, "sessao": sessao, "aba": "agenda"})

