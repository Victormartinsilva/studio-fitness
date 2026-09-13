from datetime import datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.agenda import motor
from apps.agenda.models import Sessao
from apps.avaliacoes import evolucao
from apps.cadastros.models import Aluno, Equipamento
from apps.modulos.catalogo import MODULOS
from apps.modulos.models import VisibilidadeModulo, eixo_visivel


@login_required
def home(request):
    usuario = request.user
    agora = timezone.now()
    hoje = timezone.localdate()

    sessoes = Sessao.objects.exclude(status=Sessao.Status.CANCELADA).select_related(
        "aluno", "professor__usuario", "tipo", "equipamento"
    )
    if usuario.is_professor and hasattr(usuario, "professor"):
        minhas = sessoes.filter(professor=usuario.professor)
    elif usuario.is_aluno and hasattr(usuario, "aluno"):
        minhas = sessoes.filter(aluno=usuario.aluno)
    else:
        minhas = sessoes

    proxima = minhas.filter(inicio__gte=agora).order_by("inicio").first()

    # "Hoje: N sessões" (Etapa 4.4): lista compacta pra home do professor no
    # celular, com ação rápida de marcar realizada/faltou sem precisar abrir
    # a agenda inteira.
    sessoes_hoje = []
    total_sessoes_hoje = 0
    if usuario.is_professor and hasattr(usuario, "professor"):
        inicio_hoje = timezone.make_aware(datetime.combine(hoje, time.min))
        fim_hoje = inicio_hoje + timedelta(days=1)
        hoje_qs = minhas.filter(inicio__gte=inicio_hoje, inicio__lt=fim_hoje).order_by("inicio")
        total_sessoes_hoje = hoje_qs.count()
        sessoes_hoje = list(hoje_qs[:3])

    kpis = []
    if usuario.is_superuser or usuario.is_gestor:
        # Painel não usa "próxima vaga" — pula o cálculo mais caro de
        # resumo_do_dia (um buscar_vagas por tipo de sessão ativo).
        resumo = motor.resumo_do_dia(hoje, incluir_proxima_vaga=False)
        sessoes_canceladas_hoje = resumo["por_status"].get(Sessao.Status.CANCELADA, 0)
        kpis = [
            {"valor": "{}%".format(resumo["ocupacao_pct"]), "nome": "Ocupação hoje"},
            {"valor": resumo["total_sessoes"] - sessoes_canceladas_hoje, "nome": "Sessões hoje"},
            {"valor": Aluno.objects.filter(ativo=True).count(), "nome": "Alunos ativos"},
            {"valor": Equipamento.objects.filter(status=Equipamento.Status.ATIVO).count(), "nome": "Equipamentos ativos"},
        ]

    # Resumo "Sua evolução" na home do aluno (eixo do Pacote Plus).
    resumo_evolucao = []
    aluno = getattr(usuario, "aluno", None) if usuario.is_aluno else None
    if aluno and eixo_visivel(usuario, "evolucao"):
        avaliacoes = list(aluno.avaliacoes.all()[:10])
        if avaliacoes:
            indicadores = evolucao.indicadores_atuais(avaliacoes)
            resumo_evolucao = [indicadores[c] for c in ("percentual_gordura", "massa_magra_kg") if indicadores[c]["tem_valor"]]

    modulos_previa = []
    if not (usuario.is_superuser or usuario.is_gestor):
        slugs_visiveis = set(
            VisibilidadeModulo.objects.filter(papel=usuario.papel, visivel=True).values_list("slug", flat=True)
        )
        modulos_previa = [modulo for modulo in MODULOS if not modulo.liberado and modulo.slug in slugs_visiveis]

    return render(
        request,
        "painel/home.html",
        {
            "aba": "inicio",
            "hoje": hoje,
            "proxima": proxima,
            "kpis": kpis,
            "pode_agendar": usuario.is_superuser or usuario.is_gestor or usuario.is_professor,
            "proximas_24h": minhas.filter(inicio__gte=agora, inicio__lte=agora + timedelta(hours=24)).count(),
            "modulos_previa": modulos_previa,
            "resumo_evolucao": resumo_evolucao,
            "sessoes_hoje": sessoes_hoje,
            "total_sessoes_hoje": total_sessoes_hoje,
        },
    )

