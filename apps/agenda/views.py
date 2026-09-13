from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.cadastros.models import Aluno, Equipamento, Professor, TipoSessao

from . import motor, servicos
from .forms import AgendarForm, RemararForm
from .models import Sessao
from .permissoes import _digitos, _pode_gerenciar_sessao

_SESSOES_ANTERIORES_POR_PAGINA = 20
_DIAS_SEMANA_ABREV = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def _rotulo_dia(dia, hoje):
    delta = (dia - hoje).days
    if delta == 0:
        return "Hoje"
    if delta == 1:
        return "Amanhã"
    if delta == -1:
        return "Ontem"
    return f"{_DIAS_SEMANA_ABREV[dia.weekday()]} {dia:%d/%m}"


def _agrupar_por_dia(sessoes, hoje):
    """Agrupa sessões (já ordenadas por `inicio`, crescente ou decrescente)
    em blocos consecutivos do mesmo dia — funciona nos dois sentidos porque
    só olha se o dia mudou em relação ao item anterior, nunca reordena."""
    grupos = []
    grupo_atual = None
    for sessao in sessoes:
        dia = timezone.localtime(sessao.inicio).date()
        if grupo_atual is None or grupo_atual["data"] != dia:
            grupo_atual = {"data": dia, "rotulo": _rotulo_dia(dia, hoje), "sessoes": []}
            grupos.append(grupo_atual)
        grupo_atual["sessoes"].append(sessao)
    return grupos


@login_required
def minhas_sessoes(request):
    usuario = request.user
    sessoes = Sessao.objects.exclude(status=Sessao.Status.CANCELADA).select_related(
        "professor__usuario", "aluno", "equipamento"
    )

    if usuario.is_professor and hasattr(usuario, "professor"):
        sessoes = sessoes.filter(professor=usuario.professor)
    elif usuario.is_aluno and hasattr(usuario, "aluno"):
        sessoes = sessoes.filter(aluno=usuario.aluno)

    hoje = timezone.localdate()
    inicio_hoje = timezone.make_aware(datetime.combine(hoje, time.min))

    aba_lista = "anteriores" if request.GET.get("lista") == "anteriores" else "proximas"
    pagina = None
    if aba_lista == "anteriores":
        queryset = sessoes.filter(inicio__lt=inicio_hoje).order_by("-inicio")
        paginator = Paginator(queryset, _SESSOES_ANTERIORES_POR_PAGINA)
        pagina = paginator.get_page(request.GET.get("pagina"))
        sessoes_da_pagina = pagina.object_list
    else:
        sessoes_da_pagina = sessoes.filter(inicio__gte=inicio_hoje).order_by("inicio")

    pode_agendar = usuario.is_superuser or usuario.is_gestor or usuario.is_professor
    return render(
        request,
        "agenda/minhas_sessoes.html",
        {
            "grupos": _agrupar_por_dia(sessoes_da_pagina, hoje),
            "aba_lista": aba_lista,
            "pagina": pagina,
            "pode_cancelar": pode_agendar and aba_lista == "proximas",
            "pode_agendar": pode_agendar,
            "aba": "minhas_sessoes",
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


_PERIODOS_VALIDOS = ("manha", "tarde", "noite")


@login_required
def vagas_json(request):
    """Endpoint JSON para o formulário de agendar (Etapa 3b, progressive
    enhancement via fetch): mesmos horários livres que `motor.buscar_vagas`
    devolveria para os parâmetros pedidos, em `HH:MM`. View fina — só
    valida os parâmetros de query e delega pro motor, sem duplicar
    nenhuma regra de disponibilidade."""
    if not (request.user.is_superuser or request.user.is_gestor or request.user.is_professor):
        return JsonResponse({"erro": "Você não pode consultar horários."}, status=403)

    tipo_id = request.GET.get("tipo")
    data_str = request.GET.get("data")
    professor_id = request.GET.get("professor")
    equipamento_id = request.GET.get("equipamento")
    periodo = request.GET.get("periodo") or None

    try:
        tipo = TipoSessao.objects.get(pk=tipo_id, ativo=True)
    except (TipoSessao.DoesNotExist, ValueError, TypeError):
        return JsonResponse({"erro": "Tipo de sessão inválido ou não informado."}, status=400)

    try:
        dia = date.fromisoformat(data_str)
    except (TypeError, ValueError):
        return JsonResponse({"erro": "Data inválida. Use o formato AAAA-MM-DD."}, status=400)

    professor = None
    if professor_id:
        try:
            professor = Professor.objects.get(pk=professor_id, ativo=True)
        except (Professor.DoesNotExist, ValueError, TypeError):
            return JsonResponse({"erro": "Professor inválido."}, status=400)

    equipamento = None
    if equipamento_id:
        try:
            equipamento = Equipamento.objects.get(pk=equipamento_id, status=Equipamento.Status.ATIVO)
        except (Equipamento.DoesNotExist, ValueError, TypeError):
            return JsonResponse({"erro": "Equipamento inválido."}, status=400)

    if periodo is not None and periodo not in _PERIODOS_VALIDOS:
        return JsonResponse({"erro": 'Período inválido. Use "manha", "tarde" ou "noite".'}, status=400)

    vagas = motor.buscar_vagas(
        tipo_sessao=tipo, dia=dia, professor=professor, equipamento=equipamento, periodo=periodo, limite=8
    )

    return JsonResponse(
        {
            "vagas": [
                {
                    "professor_id": vaga["professor"].pk,
                    "professor_nome": str(vaga["professor"]),
                    "equipamento_id": vaga["equipamento"].pk if vaga["equipamento"] else None,
                    "equipamento_nome": str(vaga["equipamento"]) if vaga["equipamento"] else None,
                    "inicio": timezone.localtime(vaga["inicio"]).strftime("%H:%M"),
                    "fim": timezone.localtime(vaga["fim"]).strftime("%H:%M"),
                }
                for vaga in vagas
            ]
        }
    )


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
def _redirecionar_apos_status(request, sessao):
    """Volta pra onde a ação foi disparada (ex.: painel:home, na lista
    "Hoje: N sessões") quando o form manda `next`; sem isso, cai no padrão
    de sempre (a página de detalhe da sessão)."""
    destino = request.POST.get("next", "")
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(destino)
    return redirect("agenda:detalhe", pk=sessao.pk)


@require_POST
@login_required
def status(request, pk):
    sessao = get_object_or_404(Sessao, pk=pk)
    usuario = request.user
    if not _pode_gerenciar_sessao(usuario, sessao):
        raise PermissionDenied("Você não pode mudar o status desta sessão.")

    valor = request.POST.get("status")
    valores_permitidos = {Sessao.Status.CONFIRMADA, Sessao.Status.REALIZADA, Sessao.Status.FALTOU}
    if valor not in valores_permitidos:
        messages.error(request, "Status inválido.")
        return _redirecionar_apos_status(request, sessao)

    try:
        servicos.marcar_status(sessao=sessao, status=valor, usuario=usuario)
    except ValidationError as exc:
        messages.error(request, exc.message)
    else:
        messages.success(request, f"Sessão marcada como {sessao.get_status_display().lower()}.")
    return _redirecionar_apos_status(request, sessao)


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

