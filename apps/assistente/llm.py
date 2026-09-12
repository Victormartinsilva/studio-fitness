"""
Cliente único do assistente com os provedores de LLM gratuitos (formato
OpenAI chat/completions: Groq e Gemini expõem esse mesmo formato).

Só existe uma função pública, `chamar`, pensada para ser fácil de mockar
nos testes (`unittest.mock.patch("apps.assistente.llm.chamar", ...)`) —
nenhuma chamada de rede deve acontecer durante `python manage.py test`.
"""
import httpx
from django.conf import settings


class TodosProvedoresFalharam(Exception):
    """Nenhum provedor configurado respondeu (ou nenhum tinha chave)."""


def chamar(mensagens, ferramentas=None, *, usuario_id=None):
    """Tenta cada provedor de `settings.LLM_PROVEDORES_CONFIG`, na ordem de
    `settings.LLM_PROVEDORES`, pulando os que não têm chave configurada.

    Devolve o JSON já parseado da resposta (`response.json()`) do primeiro
    provedor que responder com sucesso — quem chama extrai
    `resposta["choices"][0]["message"]`.

    `usuario_id` não é usado na chamada em si (não há por-usuário nada a
    fazer aqui); existe só para eventual log/telemetria futura.

    Levanta `TodosProvedoresFalharam` se nenhum provedor tiver chave ou se
    todos falharem (status 429/5xx, timeout, erro de conexão ou qualquer
    outro `httpx.HTTPError`).
    """
    algum_configurado = False

    for nome_provedor in settings.LLM_PROVEDORES:
        config = settings.LLM_PROVEDORES_CONFIG.get(nome_provedor)
        if not config or not config.get("chave"):
            continue
        algum_configurado = True

        payload = {
            "model": config["modelo"],
            "messages": mensagens,
            "temperature": 0.2,
            "max_tokens": 600,
        }
        if ferramentas:
            payload["tools"] = ferramentas
            payload["tool_choice"] = "auto"

        try:
            resposta = httpx.post(
                f"{config['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {config['chave']}"},
                json=payload,
                timeout=settings.LLM_TIMEOUT_S,
            )
            if resposta.status_code == 429 or resposta.status_code >= 500:
                continue
            resposta.raise_for_status()
            return resposta.json()
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
            continue

    if not algum_configurado:
        raise TodosProvedoresFalharam("Nenhum provedor de LLM está configurado (sem chave de API).")
    raise TodosProvedoresFalharam("Todos os provedores de LLM configurados falharam.")
