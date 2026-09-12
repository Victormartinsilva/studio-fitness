from dataclasses import dataclass


@dataclass(frozen=True)
class Modulo:
    slug: str
    titulo: str
    descricao: str
    fase: int
    publico: str
    liberado: bool = False


MODULOS = (
    Modulo(
        "agenda",
        "Agenda inteligente",
        "Sessões integradas a professor, equipamento, aluno e janelas de preparo.",
        1,
        "Todos os perfis",
        True,
    ),
    Modulo(
        "cadastros",
        "Aluno e relacionamento",
        "Cadastro, histórico de sessões, preferências e acompanhamento do aluno.",
        1,
        "Gestão e professores",
        True,
    ),
    Modulo(
        "avaliacoes",
        "Avaliação e evolução",
        "Medidas, indicadores e histórico visual de evolução física.",
        2,
        "Gestão e alunos",
        True,
    ),
    Modulo(
        "financeiro",
        "Gestão financeira",
        "Mensalidades, contas a receber, cobranças e inadimplência.",
        2,
        "Gestão",
    ),
    Modulo(
        "portal-aluno",
        "Portal do aluno",
        "Próximos agendamentos, saldo, frequência e evolução física.",
        3,
        "Alunos",
    ),
    Modulo(
        "automacao",
        "Automação",
        "Lembretes, WhatsApp, integrações e relatórios adicionais.",
        4,
        "Gestão",
    ),
)


def obter_modulo(slug):
    return next((modulo for modulo in MODULOS if modulo.slug == slug), None)


@dataclass(frozen=True)
class Eixo:
    """Uma seção/link real da navegação (não um módulo do roadmap) que o
    administrador pode mostrar ou esconder por perfil — ex.: os itens do
    menu que hoje só aparecem para gestor/professor por regra fixa."""

    slug: str
    rotulo: str
    papeis_padrao: tuple  # perfis (Usuario.Papel) que veem este eixo por padrão


EIXOS = (
    Eixo("meus_alunos", "Meus alunos", ("professor",)),
    Eixo("alunos", "Alunos", ("gestor",)),
    Eixo("equipamentos", "Equipamentos", ("gestor",)),
    Eixo("tipos_sessao", "Tipos de sessão", ("gestor",)),
    Eixo("planos", "Planos", ("gestor",)),
)


def obter_eixo(slug):
    return next((eixo for eixo in EIXOS if eixo.slug == slug), None)
