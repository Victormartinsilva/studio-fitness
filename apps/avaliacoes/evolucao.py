"""
Leitura visual das avaliações físicas ("Minha evolução", slide 09 da proposta):
cartões de peso/% gordura/massa magra, medidas na silhueta, gráfico por
métrica e comparação entre duas avaliações.

Tudo aqui é cálculo puro sobre uma lista de `AvaliacaoFisica` — sem request,
sem permissão. As views decidem quem pode ver o quê e só montam o contexto
com estas funções.
"""
import math
from dataclasses import dataclass

MESES_ABREV = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")
MENOS = "−"  # sinal de menos tipográfico (−), mais legível que o hífen


@dataclass(frozen=True)
class Metrica:
    campo: str
    rotulo: str
    unidade: str
    unidade_delta: str
    # "sobe"/"desce": em que direção a métrica melhora. None = depende do
    # objetivo do aluno (peso, braço…), então a variação fica em cor neutra.
    melhora: str = None


METRICAS = {
    m.campo: m
    for m in (
        Metrica("peso_kg", "Peso", "kg", "kg"),
        Metrica("percentual_gordura", "% Gordura", "%", "p.p.", "desce"),
        Metrica("massa_magra_kg", "Massa magra", "kg", "kg", "sobe"),
        Metrica("braco_cm", "Braço", "cm", "cm"),
        Metrica("cintura_cm", "Cintura", "cm", "cm", "desce"),
        Metrica("quadril_cm", "Quadril", "cm", "cm"),
        Metrica("coxa_cm", "Coxa", "cm", "cm"),
    )
}
CARTOES = ("peso_kg", "percentual_gordura", "massa_magra_kg")
MEDIDAS = ("braco_cm", "cintura_cm", "quadril_cm", "coxa_cm")
METRICAS_GRAFICO = ("percentual_gordura", "peso_kg", "massa_magra_kg", "cintura_cm", "quadril_cm", "coxa_cm", "braco_cm")
METRICA_PADRAO = "percentual_gordura"


def formatar_numero(valor):
    """64.8 -> "64,8" (sempre 1 casa, vírgula decimal pt-br)."""
    return f"{valor:.1f}".replace(".", ",")


def formatar_valor(valor, metrica):
    if valor is None:
        return "—"
    separador = "" if metrica.unidade == "%" else " "
    return f"{formatar_numero(valor)}{separador}{metrica.unidade}"


def classe_variacao(diferenca, metrica):
    if diferenca == 0 or metrica.melhora is None:
        return "neutra"
    subiu = diferenca > 0
    return "melhora" if subiu == (metrica.melhora == "sobe") else "piora"


def formatar_variacao(diferenca, metrica):
    if diferenca == 0:
        return f"0,0 {metrica.unidade_delta}"
    sinal = "+" if diferenca > 0 else MENOS
    return f"{sinal}{formatar_numero(abs(diferenca))} {metrica.unidade_delta}"


def indicador(metrica, atual, anterior, sufixo=""):
    """Um número pronto para a tela: valor atual + variação contra o anterior."""
    diferenca = atual - anterior if atual is not None and anterior is not None else None
    return {
        "campo": metrica.campo,
        "rotulo": metrica.rotulo,
        "tem_valor": atual is not None,
        "valor": formatar_valor(atual, metrica),
        "valor_anterior": formatar_valor(anterior, metrica),
        "variacao": formatar_variacao(diferenca, metrica) if diferenca is not None else "",
        "sufixo": sufixo if diferenca is not None else "",
        "classe": classe_variacao(diferenca, metrica) if diferenca is not None else "neutra",
    }


def ultimo_e_anterior(avaliacoes, campo):
    """Valores mais recente e anterior de um campo, pulando avaliações em que
    ele não foi medido (ex.: uma avaliação só com peso não "apaga" a cintura).
    `avaliacoes` vem da mais recente para a mais antiga."""
    valores = [getattr(a, campo) for a in avaliacoes if getattr(a, campo) is not None]
    return (valores[0] if valores else None), (valores[1] if len(valores) > 1 else None)


def indicadores_atuais(avaliacoes):
    """{campo: indicador} com a variação desde a última medição de cada campo."""
    resultado = {}
    for campo, metrica in METRICAS.items():
        atual, anterior = ultimo_e_anterior(avaliacoes, campo)
        resultado[campo] = indicador(metrica, atual, anterior, "desde a última")
    return resultado


def indicadores_comparacao(de, ate):
    """{campo: indicador} do valor em `ate` contra o valor em `de`."""
    sufixo = f"desde {de.data:%d/%m/%Y}"
    return {
        campo: indicador(metrica, getattr(ate, campo), getattr(de, campo), sufixo)
        for campo, metrica in METRICAS.items()
    }


def _num(valor):
    # Ponto decimal fixo: {{ }} localiza para vírgula em pt-br e quebraria
    # atributos numéricos do SVG.
    return f"{valor:.1f}"


def grafico(avaliacoes, campo, largura=640, altura=260):
    """Geometria do gráfico de linha de uma métrica (SVG montado no template).

    Eixo X igualmente espaçado por avaliação; rótulo de mês ("Mar", "Abr")
    quando há no máximo uma avaliação por mês, senão "dd/mm". Devolve None
    sem pelo menos duas medições (uma só não é evolução)."""
    metrica = METRICAS[campo]
    pontos_brutos = [(a.data, getattr(a, campo)) for a in reversed(avaliacoes) if getattr(a, campo) is not None]
    if len(pontos_brutos) < 2:
        return None

    margem_x, topo, base = 22, 30, 40
    plot_altura = altura - topo - base
    valores = [float(v) for _, v in pontos_brutos]
    minimo, maximo = min(valores), max(valores)
    folga = max((maximo - minimo) * 0.18, 0.5)
    piso, teto = minimo - folga, maximo + folga

    meses = [(d.year, d.month) for d, _ in pontos_brutos]
    por_mes = len(set(meses)) == len(meses)
    total = len(pontos_brutos)
    passo_rotulo = max(1, math.ceil(total / 7))

    pontos = []
    for indice, (data, valor) in enumerate(pontos_brutos):
        x = margem_x + (largura - 2 * margem_x) * indice / (total - 1)
        y = topo + (1 - (float(valor) - piso) / (teto - piso)) * plot_altura
        ultimo = indice == total - 1
        # Rótulo do valor atual do lado oposto ao da linha que chega nele:
        # linha vindo de cima → rótulo embaixo, e vice-versa (senão o texto
        # fica em cima do traço).
        chega_de_cima = pontos and float(pontos[-1]["y"]) < y
        pontos.append(
            {
                "x": _num(x),
                "y": _num(y),
                "rotulo_y": _num(y + 22 if chega_de_cima else y - 12),
                "raio": _num(6 if ultimo else 4.5),
                "ultimo": ultimo,
                "valor": formatar_valor(valor, metrica),
                "data": f"{data:%d/%m/%Y}",
                "eixo": (MESES_ABREV[data.month - 1] if por_mes else f"{data:%d/%m}")
                if (indice % passo_rotulo == 0 or ultimo)
                else "",
            }
        )

    return {
        "titulo": metrica.rotulo,
        "largura": largura,
        "altura": altura,
        "pontos": pontos,
        "linha": " ".join(f"{p['x']},{p['y']}" for p in pontos),
        "grade": [_num(topo + plot_altura * fracao) for fracao in (0, 0.5, 1)],
        "margem_x": margem_x,
        "fim_x": largura - margem_x,
        "eixo_y": altura - 8,
    }


def texto_compartilhar(avaliacoes):
    """Resumo do período inteiro (primeira × última avaliação) para o botão
    "Compartilhar evolução". Sem nome e sem medidas absolutas: só variações."""
    if len(avaliacoes) < 2:
        return ""
    ultima, primeira = avaliacoes[0], avaliacoes[-1]
    partes = []
    for campo in ("percentual_gordura", "massa_magra_kg", "peso_kg", "cintura_cm"):
        metrica = METRICAS[campo]
        inicio, fim = getattr(primeira, campo), getattr(ultima, campo)
        if inicio is not None and fim is not None and fim != inicio:
            partes.append(f"{metrica.rotulo.lower()} {formatar_variacao(fim - inicio, metrica)}")
    if not partes:
        return ""
    periodo = f"{MESES_ABREV[primeira.data.month - 1].lower()}/{primeira.data:%Y} a " \
              f"{MESES_ABREV[ultima.data.month - 1].lower()}/{ultima.data:%Y}"
    return f"Minha evolução no Studio Fitness ({periodo}): " + " · ".join(partes) + " 💪"


def contexto_painel(avaliacoes, metrica_pedida=None):
    """Tudo que o painel "Minha evolução" precisa, a partir das avaliações do
    aluno (mais recente primeiro)."""
    campo = metrica_pedida if metrica_pedida in METRICAS_GRAFICO else METRICA_PADRAO
    indicadores = indicadores_atuais(avaliacoes)
    geometria_grande = grafico(avaliacoes, campo)
    return {
        "avaliacoes": avaliacoes,
        "ultima": avaliacoes[0] if avaliacoes else None,
        "primeira": avaliacoes[-1] if avaliacoes else None,
        "cartoes": [indicadores[c] for c in CARTOES],
        "medidas": {c.replace("_cm", ""): indicadores[c] for c in MEDIDAS},
        "metrica_ativa": METRICAS[campo],
        "chips_metrica": [
            {"campo": c, "rotulo": METRICAS[c].rotulo, "ativo": c == campo} for c in METRICAS_GRAFICO
        ],
        "grafico": geometria_grande,
        "grafico_compacto": grafico(avaliacoes, campo, largura=310, altura=200) if geometria_grande else None,
        "texto_compartilhar": texto_compartilhar(avaliacoes),
    }
