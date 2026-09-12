"""
Ferramentas (tools) expostas ao modelo de linguagem do assistente.

Cada ferramenta recebe `usuario` (sempre o `request.user` de quem está
conversando — NUNCA um valor escolhido pelo modelo) como primeiro
argumento, seguido dos argumentos que o próprio modelo decide passar.
Nenhuma ferramenta grava nada no banco: as duas que preparam uma ação
(`propor_agendamento`/`propor_cancelamento`) só validam e devolvem um
token assinado; a gravação de fato só acontece em `views.confirmar`,
via `apps.agenda.servicos` — a única porta de entrada para mudar uma
`Sessao`.

Toda ferramenta devolve um dict simples (str/int/float/bool/None/list/
dict) pronto para virar JSON — nunca instâncias de model — e nunca deixa
uma exceção (DoesNotExist, ValueError de parsing de data/hora etc.) subir
crua: erros esperados voltam como `{"erro": "<código>", "mensagem": "..."}`.
"""
from datetime import date, datetime, time, timedelta

from django.core import signing
from django.utils import timezone

from apps.agenda import motor
from apps.agenda.models import Sessao
from apps.cadastros.models import Aluno, Equipamento, Professor, TipoSessao

TOKEN_SALT = "assistente"
TOKEN_MAX_AGE_S = 600  # 10 minutos

_DIAS_SEMANA_ABREV = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]


def _erro(codigo, mensagem):
    return {"erro": codigo, "mensagem": mensagem}


def _permissao_negada(mensagem="Você não pode usar esse recurso."):
    return _erro("permissao_negada", mensagem)


def _nao_encontrado(mensagem):
    return _erro("nao_encontrado", mensagem)


def _parametro_invalido(mensagem):
    return _erro("parametro_invalido", mensagem)


def _parse_data(valor):
    """Espera 'AAAA-MM-DD'. Levanta ValueError com mensagem amigável."""
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        raise ValueError(f'Data inválida: "{valor}". Use o formato AAAA-MM-DD.')


def _parse_hora(valor):
    """Espera 'HH:MM' (ou 'HH:MM:SS'). Levanta ValueError com mensagem amigável."""
    try:
        return time.fromisoformat(valor)
    except (TypeError, ValueError):
        raise ValueError(f'Horário inválido: "{valor}". Use o formato HH:MM.')


def _formatar_quando(dia, hora):
    abrev = _DIAS_SEMANA_ABREV[dia.weekday()]
    return f"{abrev} {dia:%d/%m} {hora:%H:%M}"


def resumo_do_dia(usuario, data):
    try:
        dia = _parse_data(data)
    except ValueError as exc:
        return _parametro_invalido(str(exc))

    resumo = motor.resumo_do_dia(dia)

    if usuario.is_aluno and not (usuario.is_gestor or usuario.is_superuser):
        # Aluno só vê a ocupação geral do dia — nada sobre outros alunos,
        # professores ou equipamentos específicos.
        return {
            "ocupacao_pct": resumo["ocupacao_pct"],
            "total_sessoes": resumo["total_sessoes"],
        }

    proxima_vaga = resumo["proxima_vaga"]
    if proxima_vaga:
        proxima_vaga = {
            "professor": str(proxima_vaga["professor"]),
            "equipamento": str(proxima_vaga["equipamento"]) if proxima_vaga["equipamento"] else None,
            "inicio": proxima_vaga["inicio"].isoformat(),
            "fim": proxima_vaga["fim"].isoformat(),
        }

    return {
        "total_sessoes": resumo["total_sessoes"],
        "por_status": resumo["por_status"],
        "por_professor": resumo["por_professor"],
        "por_equipamento": resumo["por_equipamento"],
        "alunos_distintos": resumo["alunos_distintos"],
        "ocupacao_pct": resumo["ocupacao_pct"],
        "proxima_vaga": proxima_vaga,
    }


def listar_sessoes(usuario, data, professor_id=None):
    if not (usuario.is_gestor or usuario.is_professor or usuario.is_superuser):
        return _permissao_negada("Só gestores e professores podem listar sessões.")

    try:
        dia = _parse_data(data)
    except ValueError as exc:
        return _parametro_invalido(str(exc))

    inicio_dia = timezone.make_aware(datetime.combine(dia, time.min))
    fim_dia = timezone.make_aware(datetime.combine(dia, time.max))

    sessoes = Sessao.objects.filter(inicio__gte=inicio_dia, inicio__lte=fim_dia).exclude(
        status=Sessao.Status.CANCELADA
    )

    if usuario.is_professor and not usuario.is_gestor and not usuario.is_superuser:
        if not hasattr(usuario, "professor"):
            return _permissao_negada("Seu usuário não está vinculado a um cadastro de professor.")
        # Professor só vê as próprias sessões, mesmo se pedir outro professor_id.
        sessoes = sessoes.filter(professor=usuario.professor)
    elif professor_id is not None:
        try:
            professor = Professor.objects.get(pk=professor_id)
        except (Professor.DoesNotExist, ValueError, TypeError):
            return _nao_encontrado("Professor não encontrado.")
        sessoes = sessoes.filter(professor=professor)

    sessoes = sessoes.select_related("professor__usuario", "aluno", "tipo", "equipamento").order_by("inicio")

    return {
        "sessoes": [
            {
                "id": s.pk,
                "aluno": s.aluno.nome,
                "professor": str(s.professor),
                "tipo": s.tipo.nome,
                "equipamento": str(s.equipamento) if s.equipamento else None,
                "inicio": s.inicio.isoformat(),
                "fim": s.fim.isoformat(),
                "status": s.status,
            }
            for s in sessoes
        ]
    }


def listar_tipos_sessao(usuario):
    tipos = TipoSessao.objects.filter(ativo=True).order_by("nome")
    return {
        "tipos_sessao": [
            {"id": t.pk, "nome": t.nome, "duracao_min": t.duracao_min} for t in tipos
        ]
    }


def buscar_aluno(usuario, nome):
    if not (usuario.is_gestor or usuario.is_professor or usuario.is_superuser):
        return _permissao_negada("Só gestores e professores podem buscar alunos.")

    if not nome or not str(nome).strip():
        return _parametro_invalido("Informe um nome (ou parte dele) para buscar.")

    alunos = Aluno.objects.filter(ativo=True, nome__icontains=nome).order_by("nome")[:5]
    return {"alunos": [{"id": a.pk, "nome": a.nome} for a in alunos]}


def buscar_vagas(usuario, tipo_id, data, periodo=None, hora=None, professor_id=None, equipamento_id=None):
    if not (usuario.is_gestor or usuario.is_professor or usuario.is_superuser):
        return _permissao_negada("Só gestores e professores podem buscar vagas.")

    try:
        dia = _parse_data(data)
        hora_desejada = _parse_hora(hora) if hora else None
    except ValueError as exc:
        return _parametro_invalido(str(exc))

    try:
        tipo = TipoSessao.objects.get(pk=tipo_id)
    except (TipoSessao.DoesNotExist, ValueError, TypeError):
        return _nao_encontrado("Tipo de sessão não encontrado.")
    if not tipo.ativo:
        return _parametro_invalido("Esse tipo de sessão está inativo.")

    professor = None
    if professor_id is not None:
        try:
            professor = Professor.objects.get(pk=professor_id)
        except (Professor.DoesNotExist, ValueError, TypeError):
            return _nao_encontrado("Professor não encontrado.")

    equipamento = None
    if equipamento_id is not None:
        try:
            equipamento = Equipamento.objects.get(pk=equipamento_id)
        except (Equipamento.DoesNotExist, ValueError, TypeError):
            return _nao_encontrado("Equipamento não encontrado.")

    if periodo is not None:
        try:
            motor._limites_periodo(periodo)
        except ValueError as exc:
            return _parametro_invalido(str(exc))

    vagas = motor.buscar_vagas(
        tipo_sessao=tipo,
        dia=dia,
        professor=professor,
        equipamento=equipamento,
        hora_desejada=hora_desejada,
        periodo=periodo,
        limite=8,
    )

    return {
        "vagas": [
            {
                "professor_id": v["professor"].pk,
                "professor_nome": str(v["professor"]),
                "equipamento_id": v["equipamento"].pk if v["equipamento"] else None,
                "equipamento_nome": str(v["equipamento"]) if v["equipamento"] else None,
                "inicio": v["inicio"].isoformat(),
                "fim": v["fim"].isoformat(),
            }
            for v in vagas
        ]
    }


def propor_agendamento(usuario, aluno_id, tipo_id, professor_id, data, hora, equipamento_id=None):
    if not (usuario.is_gestor or usuario.is_professor or usuario.is_superuser):
        return _permissao_negada("Só gestores e professores podem propor agendamentos.")

    try:
        dia = _parse_data(data)
        hora_inicio = _parse_hora(hora)
    except ValueError as exc:
        return _parametro_invalido(str(exc))

    try:
        aluno = Aluno.objects.get(pk=aluno_id)
    except (Aluno.DoesNotExist, ValueError, TypeError):
        return _nao_encontrado("Aluno não encontrado.")
    if not aluno.ativo:
        return _parametro_invalido("Esse aluno está inativo.")

    try:
        tipo = TipoSessao.objects.get(pk=tipo_id)
    except (TipoSessao.DoesNotExist, ValueError, TypeError):
        return _nao_encontrado("Tipo de sessão não encontrado.")
    if not tipo.ativo:
        return _parametro_invalido("Esse tipo de sessão está inativo.")

    try:
        professor = Professor.objects.get(pk=professor_id)
    except (Professor.DoesNotExist, ValueError, TypeError):
        return _nao_encontrado("Professor não encontrado.")

    equipamento = None
    if equipamento_id is not None:
        try:
            equipamento = Equipamento.objects.get(pk=equipamento_id)
        except (Equipamento.DoesNotExist, ValueError, TypeError):
            return _nao_encontrado("Equipamento não encontrado.")

    inicio = timezone.make_aware(datetime.combine(dia, hora_inicio))
    fim = inicio + timedelta(minutes=tipo.duracao_min)

    motivo = motor.motivo_indisponibilidade(professor, equipamento, inicio, fim, tipo, aluno)
    if motivo:
        return {"disponivel": False, "motivo": motivo}

    token = signing.dumps(
        {
            "acao": "agendar",
            "aluno_id": aluno.pk,
            "tipo_id": tipo.pk,
            "professor_id": professor.pk,
            "equipamento_id": equipamento.pk if equipamento else None,
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
            "usuario_id": usuario.pk,
        },
        salt=TOKEN_SALT,
    )
    resumo = (
        f"{aluno.nome} · {tipo.nome} {tipo.duracao_min}min · {professor} · "
        f"{equipamento if equipamento else 'sem equipamento'} · {_formatar_quando(dia, hora_inicio)}"
    )
    return {"disponivel": True, "token": token, "resumo": resumo}


def propor_cancelamento(usuario, sessao_id, justificativa=""):
    try:
        sessao = Sessao.objects.select_related("professor__usuario", "aluno", "tipo", "equipamento").get(
            pk=sessao_id
        )
    except (Sessao.DoesNotExist, ValueError, TypeError):
        return _nao_encontrado("Sessão não encontrada.")

    dono = usuario.is_professor and hasattr(usuario, "professor") and sessao.professor_id == usuario.professor.pk
    if not (usuario.is_gestor or usuario.is_superuser or dono):
        return _permissao_negada("Você só pode cancelar suas próprias sessões.")

    if sessao.status == Sessao.Status.CANCELADA:
        return _parametro_invalido("Essa sessão já está cancelada.")

    token = signing.dumps(
        {
            "acao": "cancelar",
            "sessao_id": sessao.pk,
            "justificativa": justificativa or "",
            "usuario_id": usuario.pk,
        },
        salt=TOKEN_SALT,
    )
    resumo = (
        f"Cancelar: {sessao.aluno.nome} · {sessao.tipo.nome} · {sessao.professor} · "
        f"{_formatar_quando(timezone.localtime(sessao.inicio).date(), timezone.localtime(sessao.inicio).time())}"
    )
    return {"disponivel": True, "token": token, "resumo": resumo}


REGISTRO = {
    "resumo_do_dia": {
        "funcao": resumo_do_dia,
        "schema": {
            "type": "function",
            "function": {
                "name": "resumo_do_dia",
                "description": "Resumo administrativo de um dia: total de sessões, ocupação, etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "data": {"type": "string", "description": "Data no formato AAAA-MM-DD."},
                    },
                    "required": ["data"],
                },
            },
        },
    },
    "listar_sessoes": {
        "funcao": listar_sessoes,
        "schema": {
            "type": "function",
            "function": {
                "name": "listar_sessoes",
                "description": "Lista as sessões agendadas (não canceladas) de um dia. Só gestor/professor.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "data": {"type": "string", "description": "Data no formato AAAA-MM-DD."},
                        "professor_id": {
                            "type": "integer",
                            "description": "Filtra por um professor específico (gestor apenas).",
                        },
                    },
                    "required": ["data"],
                },
            },
        },
    },
    "listar_tipos_sessao": {
        "funcao": listar_tipos_sessao,
        "schema": {
            "type": "function",
            "function": {
                "name": "listar_tipos_sessao",
                "description": "Lista os tipos de sessão ativos, com nome e duração em minutos.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    },
    "buscar_aluno": {
        "funcao": buscar_aluno,
        "schema": {
            "type": "function",
            "function": {
                "name": "buscar_aluno",
                "description": "Busca alunos ativos pelo nome (ou parte do nome). Só gestor/professor.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "nome": {"type": "string", "description": "Nome ou parte do nome do aluno."},
                    },
                    "required": ["nome"],
                },
            },
        },
    },
    "buscar_vagas": {
        "funcao": buscar_vagas,
        "schema": {
            "type": "function",
            "function": {
                "name": "buscar_vagas",
                "description": (
                    "Busca horários livres (professor + equipamento) para um tipo de sessão em um dia. "
                    "Só gestor/professor."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tipo_id": {"type": "integer", "description": "ID do tipo de sessão."},
                        "data": {"type": "string", "description": "Data no formato AAAA-MM-DD."},
                        "periodo": {
                            "type": "string",
                            "enum": ["manha", "tarde", "noite"],
                            "description": "Período do dia preferido.",
                        },
                        "hora": {"type": "string", "description": "Horário desejado, formato HH:MM."},
                        "professor_id": {"type": "integer", "description": "Professor preferido."},
                        "equipamento_id": {"type": "integer", "description": "Equipamento preferido."},
                    },
                    "required": ["tipo_id", "data"],
                },
            },
        },
    },
    "propor_agendamento": {
        "funcao": propor_agendamento,
        "schema": {
            "type": "function",
            "function": {
                "name": "propor_agendamento",
                "description": (
                    "Valida e prepara (sem gravar) um agendamento para aluno/tipo/professor/horário "
                    "escolhidos. Devolve um token que o usuário confirma clicando em 'Confirmar'. "
                    "Só gestor/professor."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "aluno_id": {"type": "integer"},
                        "tipo_id": {"type": "integer"},
                        "professor_id": {"type": "integer"},
                        "equipamento_id": {"type": "integer"},
                        "data": {"type": "string", "description": "Data no formato AAAA-MM-DD."},
                        "hora": {"type": "string", "description": "Horário de início, formato HH:MM."},
                    },
                    "required": ["aluno_id", "tipo_id", "professor_id", "data", "hora"],
                },
            },
        },
    },
    "propor_cancelamento": {
        "funcao": propor_cancelamento,
        "schema": {
            "type": "function",
            "function": {
                "name": "propor_cancelamento",
                "description": (
                    "Valida e prepara (sem cancelar de fato) o cancelamento de uma sessão. Devolve um "
                    "token que o usuário confirma clicando em 'Confirmar'. Gestor, ou o professor dono "
                    "da sessão."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sessao_id": {"type": "integer"},
                        "justificativa": {"type": "string"},
                    },
                    "required": ["sessao_id"],
                },
            },
        },
    },
}
