"""
Views do assistente: só dois endpoints JSON.

- POST /assistente/mensagem: manda a mensagem do usuário pro loop de
  conversa (`conversa.processar_mensagem`) e devolve a resposta + os
  cartões de confirmação (se alguma proposta de agendamento/cancelamento
  foi feita nessa rodada).
- POST /assistente/confirmar: recebe o token de uma proposta, revalida
  (o horário pode ter sido ocupado entre a proposta e o clique) e, se
  ainda válido, grava de fato via `apps.agenda.servicos`.

Ambas exigem login e ficam indisponíveis (404) se `settings.ASSISTENTE_ATIVO`
for False — assim, sem chave de API configurada, a rota nem existe.
"""
import json
from datetime import datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core import signing
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.agenda import motor, servicos
from apps.agenda.models import Sessao
from apps.cadastros.models import Aluno, Equipamento, Professor, TipoSessao

from . import conversa
from .ferramentas import TOKEN_SALT

DETALHE_VIA_ASSISTENTE = "via assistente"


def _exigir_assistente_ativo():
    if not settings.ASSISTENTE_ATIVO:
        raise Http404("Assistente desativado.")


def _corpo_json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return {}


@require_GET
@login_required
def historico(request):
    """Últimas mensagens da conversa (guardadas em `request.session` por
    `conversa.processar_mensagem`) — usado pelo JS pra repopular o chat
    quando o painel é reaberto depois de navegar pra outra página."""
    _exigir_assistente_ativo()
    return JsonResponse({"mensagens": request.session.get(conversa.SESSION_KEY_HISTORICO, [])})


@require_POST
@login_required
def mensagem(request):
    _exigir_assistente_ativo()

    dados = _corpo_json(request)
    texto = (dados.get("mensagem") or "").strip()
    if not texto:
        return JsonResponse({"erro": "parametro_invalido", "mensagem": "Mensagem vazia."}, status=400)

    resultado = conversa.processar_mensagem(request, texto)
    return JsonResponse(resultado)


@require_POST
@login_required
def confirmar(request):
    _exigir_assistente_ativo()

    dados = _corpo_json(request)
    token = dados.get("token") or ""

    try:
        proposta = signing.loads(token, salt=TOKEN_SALT, max_age=600)
    except signing.SignatureExpired:
        return JsonResponse({"ok": False, "erro": "token_expirado", "mensagem": "Proposta expirada, peça de novo."}, status=400)
    except signing.BadSignature:
        return JsonResponse({"ok": False, "erro": "token_invalido", "mensagem": "Proposta inválida."}, status=400)

    if proposta.get("usuario_id") != request.user.id:
        return JsonResponse(
            {"ok": False, "erro": "permissao_negada", "mensagem": "Essa proposta não é sua."}, status=403
        )

    acao = proposta.get("acao")
    if acao == "agendar":
        return _confirmar_agendamento(request, proposta)
    if acao == "cancelar":
        return _confirmar_cancelamento(request, proposta)
    return JsonResponse({"ok": False, "erro": "token_invalido", "mensagem": "Proposta inválida."}, status=400)


def _confirmar_agendamento(request, proposta):
    try:
        aluno = Aluno.objects.get(pk=proposta["aluno_id"])
        tipo = TipoSessao.objects.get(pk=proposta["tipo_id"])
        professor = Professor.objects.get(pk=proposta["professor_id"])
        equipamento = (
            Equipamento.objects.get(pk=proposta["equipamento_id"])
            if proposta.get("equipamento_id")
            else None
        )
        inicio = datetime.fromisoformat(proposta["inicio"])
        fim = datetime.fromisoformat(proposta["fim"])
    except (KeyError, ValueError, TypeError):
        return JsonResponse({"ok": False, "mensagem": "Proposta inválida."}, status=400)
    except (Aluno.DoesNotExist, TipoSessao.DoesNotExist, Professor.DoesNotExist, Equipamento.DoesNotExist):
        return JsonResponse(
            {"ok": False, "mensagem": "Algum dado dessa proposta não existe mais."}, status=409
        )

    if not timezone.is_aware(inicio):
        inicio = timezone.make_aware(inicio)
    if not timezone.is_aware(fim):
        fim = timezone.make_aware(fim)

    # O horário pode ter sido ocupado por outra sessão entre a proposta e
    # o clique em Confirmar — por isso revalida antes de gravar.
    motivo = motor.motivo_indisponibilidade(professor, equipamento, inicio, fim, tipo, aluno)
    if motivo:
        return JsonResponse({"ok": False, "motivo": motivo}, status=409)

    try:
        sessao = servicos.agendar(
            professor=professor,
            aluno=aluno,
            tipo=tipo,
            equipamento=equipamento,
            inicio=inicio,
            fim=fim,
            usuario=request.user,
            detalhe=DETALHE_VIA_ASSISTENTE,
        )
    except ValidationError as exc:
        return JsonResponse({"ok": False, "motivo": "; ".join(exc.messages)}, status=409)

    return JsonResponse({"ok": True, "sessao_id": sessao.pk})


def _confirmar_cancelamento(request, proposta):
    try:
        sessao = Sessao.objects.select_related("professor__usuario").get(pk=proposta["sessao_id"])
    except (Sessao.DoesNotExist, KeyError, TypeError):
        return JsonResponse({"ok": False, "mensagem": "Sessão não encontrada."}, status=409)

    dono = (
        request.user.is_professor
        and hasattr(request.user, "professor")
        and sessao.professor_id == request.user.professor.pk
    )
    if not (request.user.is_gestor or request.user.is_superuser or dono):
        return JsonResponse(
            {"ok": False, "erro": "permissao_negada", "mensagem": "Você não pode cancelar essa sessão."},
            status=403,
        )

    if sessao.status == Sessao.Status.CANCELADA:
        return JsonResponse({"ok": False, "motivo": "Essa sessão já está cancelada."}, status=409)

    sessao = servicos.cancelar(
        sessao=sessao,
        justificativa=proposta.get("justificativa", ""),
        usuario=request.user,
        detalhe=DETALHE_VIA_ASSISTENTE,
    )
    return JsonResponse({"ok": True, "sessao_id": sessao.pk})
