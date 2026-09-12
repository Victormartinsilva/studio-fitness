from .catalogo import EIXOS
from .models import VisibilidadeEixo


def eixos_visiveis(request):
    """Disponibiliza `eixos_visiveis` em todos os templates: um dicionário
    {slug: bool} dizendo se cada eixo de navegação (Meus alunos, Alunos,
    Equipamentos, Tipos de sessão, Planos...) deve aparecer para o usuário
    logado. Por padrão todo eixo é visível para os perfis listados em seu
    `papeis_padrao`; o administrador pode esconder eixos específicos em
    /modulos/visoes/, o que cria um registro VisibilidadeEixo(visivel=False)."""
    usuario = getattr(request, "user", None)
    if not usuario or not usuario.is_authenticated:
        return {}

    papel = getattr(usuario, "papel", None)
    ocultos = set(
        VisibilidadeEixo.objects.filter(papel=papel, visivel=False).values_list("slug", flat=True)
    )
    return {
        "eixos_visiveis": {
            eixo.slug: papel in eixo.papeis_padrao and eixo.slug not in ocultos for eixo in EIXOS
        }
    }
