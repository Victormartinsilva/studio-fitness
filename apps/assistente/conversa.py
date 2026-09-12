"""
Loop de conversa do assistente: monta o prompt (system + histórico + nova
mensagem), manda pro LLM junto com as ferramentas disponíveis, executa as
tool calls que o modelo pedir e repete até o modelo devolver uma resposta
final (sem tool_calls) ou até estourar o limite de rodadas.

Este módulo não fala com o LLM diretamente por HTTP — sempre via
`apps.assistente.llm.chamar`, que é o ponto mockado nos testes.
"""
import json

from django.core.cache import cache
from django.conf import settings
from django.utils import timezone

from . import llm
from .ferramentas import REGISTRO

MAX_RODADAS_TOOL_CALLS = 4
HISTORICO_MAX_MENSAGENS = 8
SESSION_KEY_HISTORICO = "assistente_historico"

_DIAS_SEMANA_PT = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]

_FERRAMENTAS_SCHEMAS = [item["schema"] for item in REGISTRO.values()]

# Nomes de ferramentas cujo retorno com sucesso vira um "cartão de
# confirmação" no frontend — montado a partir do dict que a própria
# ferramenta devolveu, nunca do texto que o modelo escreve por cima.
_FERRAMENTAS_DE_PROPOSTA = {"propor_agendamento", "propor_cancelamento"}


def _montar_system_prompt(usuario):
    agora = timezone.localtime(timezone.now())
    dia_semana = _DIAS_SEMANA_PT[agora.weekday()]
    nome_completo = usuario.get_full_name() or usuario.get_username()
    primeiro_nome = nome_completo.split()[0] if nome_completo else usuario.get_username()
    papel = getattr(usuario, "papel", "")

    return (
        "Você é o assistente da agenda do Studio Fitness. Responda em português, curto e "
        "objetivo. Nunca invente horários, vagas ou nomes. Sempre consulte as ferramentas. "
        "Para agendar, use propor_agendamento e peça ao usuário para clicar em Confirmar. "
        "Se faltar aluno, tipo ou data, pergunte. Se não houver vaga, ofereça as alternativas "
        "de buscar_vagas (outro professor, outro equipamento, outro horário).\n"
        f"Data e hora atual: {agora:%d/%m/%Y %H:%M}, {dia_semana}. "
        f"Usuário logado: {primeiro_nome} (papel: {papel})."
    )


def _chave_rate_limit(usuario_id):
    janela = int(timezone.now().timestamp() // settings.ASSISTENTE_RATE_LIMIT_JANELA_S)
    return f"assistente:rl:{usuario_id}:{janela}"


def _rate_limit_excedido(usuario_id):
    """Contador simples por usuário/janela no cache padrão (LocMemCache —
    por processo, não compartilhado entre workers do gunicorn em produção;
    aceitável para um limite best-effort num app de baixo tráfego)."""
    chave = _chave_rate_limit(usuario_id)
    contagem = cache.get(chave)
    if contagem is None:
        cache.set(chave, 1, timeout=settings.ASSISTENTE_RATE_LIMIT_JANELA_S)
        return False
    if contagem >= settings.ASSISTENTE_RATE_LIMIT_MSGS:
        return True
    try:
        cache.incr(chave)
    except ValueError:
        cache.set(chave, 1, timeout=settings.ASSISTENTE_RATE_LIMIT_JANELA_S)
    return False


def _executar_tool_call(usuario, tool_call):
    """Executa uma tool call pedida pelo modelo, sempre devolvendo um dict
    (nunca deixa exceção subir — vira erro genérico de ferramenta)."""
    nome = tool_call.get("function", {}).get("name")
    args_brutos = tool_call.get("function", {}).get("arguments") or "{}"

    entrada = REGISTRO.get(nome)
    if entrada is None:
        return nome, {"erro": "ferramenta_desconhecida", "mensagem": f'Ferramenta "{nome}" não existe.'}

    try:
        args = json.loads(args_brutos) if isinstance(args_brutos, str) else (args_brutos or {})
        if not isinstance(args, dict):
            raise ValueError("argumentos não são um objeto")
    except (TypeError, ValueError):
        return nome, {"erro": "parametro_invalido", "mensagem": "Não entendi os parâmetros pedidos."}

    try:
        resultado = entrada["funcao"](usuario, **args)
    except TypeError:
        resultado = {"erro": "parametro_invalido", "mensagem": "Faltou ou sobrou algum parâmetro nessa ação."}
    except Exception:  # noqa: BLE001 — nenhuma tool pode virar 500 do endpoint
        resultado = {"erro": "interno", "mensagem": "Não consegui executar essa ação agora."}

    return nome, resultado


def _resposta_indisponivel():
    return {"resposta": "Assistente indisponível agora, use o botão + Agendar.", "cartoes": []}


def processar_mensagem(request, mensagem_usuario):
    """Ponto de entrada chamado pela view. `request` dá acesso ao usuário
    logado (dono de toda ferramenta chamada) e à sessão (histórico)."""
    usuario = request.user

    if _rate_limit_excedido(usuario.id):
        return {
            "resposta": "Você atingiu o limite de mensagens por agora, tente de novo em alguns minutos.",
            "cartoes": [],
        }

    historico = request.session.get(SESSION_KEY_HISTORICO, [])
    mensagens = (
        [{"role": "system", "content": _montar_system_prompt(usuario)}]
        + list(historico)
        + [{"role": "user", "content": mensagem_usuario}]
    )

    cartoes = []
    texto_final = ""
    rodada = 0

    while True:
        try:
            resposta_llm = llm.chamar(mensagens, _FERRAMENTAS_SCHEMAS, usuario_id=usuario.id)
        except llm.TodosProvedoresFalharam:
            return _resposta_indisponivel()

        try:
            mensagem = resposta_llm["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            return _resposta_indisponivel()

        tool_calls = mensagem.get("tool_calls")
        if not tool_calls:
            texto_final = mensagem.get("content") or ""
            break

        rodada += 1
        if rodada > MAX_RODADAS_TOOL_CALLS:
            texto_final = "Não consegui concluir, tente reformular o seu pedido."
            break

        mensagens.append(mensagem)
        for tool_call in tool_calls:
            nome, resultado = _executar_tool_call(usuario, tool_call)
            if nome in _FERRAMENTAS_DE_PROPOSTA and not resultado.get("erro") and resultado.get("disponivel"):
                cartoes.append(resultado)
            mensagens.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "name": nome,
                    "content": json.dumps(resultado, ensure_ascii=False),
                }
            )

    novo_historico = list(historico) + [
        {"role": "user", "content": mensagem_usuario},
        {"role": "assistant", "content": texto_final},
    ]
    request.session[SESSION_KEY_HISTORICO] = novo_historico[-HISTORICO_MAX_MENSAGENS:]

    return {"resposta": texto_final, "cartoes": cartoes}
