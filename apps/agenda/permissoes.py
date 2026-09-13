"""Helpers de permissão da agenda, compartilhados por `views.py` (páginas de
detalhe/status/remarcar/cancelar) e `grade.py` (bottom sheet de ação anexado
a cada bloco de sessão da grade) — extraído da Etapa 2c-ii para evitar
duplicar a mesma regra nos dois módulos."""
import re


def _pode_gerenciar_sessao(usuario, sessao):
    """Só gestor, superuser ou o professor DONO da sessão podem mudar
    status, remarcar ou cancelar. Usada por `views.py` (`status`,
    `remarcar`, `cancelar`, `detalhe`) e por `grade.py` (para decidir se
    anexa os botões de ação ao bottom sheet de um bloco de sessão)."""
    return (
        usuario.is_superuser
        or usuario.is_gestor
        or (usuario.is_professor and hasattr(usuario, "professor") and sessao.professor_id == usuario.professor.id)
    )


def _digitos(texto):
    """Extrai só os dígitos de um telefone cadastrado (remove espaços,
    parênteses, traços etc.), para montar o link `https://wa.me/55...`."""
    return re.sub(r"\D", "", texto or "")
