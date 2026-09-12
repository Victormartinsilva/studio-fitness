"""
Visão de mês da agenda: navegação de alto nível sobre a grade diária
(apps/agenda/grade.py). Mesma leitura de dados (motor.contagem_por_dia),
layout de calendário tradicional em vez de pista por equipamento.
"""
import calendar
from datetime import date

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from . import motor
from .models import Sessao

DIA_SEMANA_INICIAL = calendar.SUNDAY  # calendários no Brasil começam no domingo

# Cor do pontinho de status no calendário de mês, por status da sessão —
# mesma linguagem de cor já usada em .tag.ok/.aviso/.critico no resto do
# app (verde = ok, vermelho = atenção), mais um cinza neutro pra cancelada.
_COR_POR_STATUS = {
    Sessao.Status.AGENDADA: "roxo",
    Sessao.Status.CONFIRMADA: "verde",
    Sessao.Status.REALIZADA: "verde",
    Sessao.Status.FALTOU: "vermelho",
    Sessao.Status.CANCELADA: "cinza",
}
# Ordem de exibição dos pontos (não a ordem do enum de status): o que pede
# mais atenção primeiro.
_ORDEM_PONTOS = ("vermelho", "roxo", "verde", "cinza")


def _mes_ano_seguro(request, hoje):
    """Lê `?ano=&mes=` da querystring, com fallback pro mês atual,
    normalização de mês fora de 1..12 (navegação vira o ano) e fallback
    também quando o ano resultante não é um ano de calendário válido
    (`datetime.date` só aceita 1..9999) — sem isso, `?ano=0` ou um número
    fora da faixa derruba a página com erro 500."""
    try:
        ano = int(request.GET.get("ano", hoje.year))
        mes = int(request.GET.get("mes", hoje.month))
    except (TypeError, ValueError):
        return hoje.year, hoje.month
    ano += (mes - 1) // 12
    mes = (mes - 1) % 12 + 1
    try:
        date(ano, mes, 1)
    except (ValueError, OverflowError):
        return hoje.year, hoje.month
    return ano, mes


@login_required
def mes(request):
    hoje = timezone.localdate()
    ano, mes_num = _mes_ano_seguro(request, hoje)

    cal = calendar.Calendar(firstweekday=DIA_SEMANA_INICIAL)
    try:
        # Mesmo com `ano`/`mes` validados, os dias de padding no início/fim
        # da grade (pra completar a semana) pertencem ao mês anterior ou
        # seguinte — perto dos limites de `date` (ano 1 ou 9999),
        # `itermonthdates` pode precisar de um dia em ano 0 ou 10000 e
        # levantar `ValueError` mesmo assim.
        dias_do_mes = list(cal.itermonthdates(ano, mes_num))  # já vem em semanas completas
    except ValueError:
        ano, mes_num = hoje.year, hoje.month
        dias_do_mes = list(cal.itermonthdates(ano, mes_num))

    contagem = motor.contagem_por_dia_e_status(dias_do_mes[0], dias_do_mes[-1])

    dias = []
    total_mes = 0
    for data_dia in dias_do_mes:
        por_status = contagem.get(data_dia, {})
        qtd = sum(q for status, q in por_status.items() if status != Sessao.Status.CANCELADA)
        cores_do_dia = {_COR_POR_STATUS[status] for status, q in por_status.items() if q > 0}
        pontos = [cor for cor in _ORDEM_PONTOS if cor in cores_do_dia]
        no_mes = data_dia.month == mes_num
        if no_mes:
            total_mes += qtd
        dias.append({
            "data": data_dia,
            "no_mes": no_mes,
            "hoje": data_dia == hoje,
            "qtd": qtd,
            "pontos": pontos,
        })

    mes_anterior = mes_num - 1 or 12
    ano_mes_anterior = ano - 1 if mes_num == 1 else ano
    mes_seguinte = mes_num + 1 if mes_num < 12 else 1
    ano_mes_seguinte = ano + 1 if mes_num == 12 else ano

    return render(request, "agenda/mes.html", {
        "aba": "agenda",
        "ano": ano,
        "mes": mes_num,
        "referencia": date(ano, mes_num, 1),
        "dias": dias,
        "total_mes": total_mes,
        "ano_mes_anterior": ano_mes_anterior, "mes_anterior": mes_anterior,
        "ano_mes_seguinte": ano_mes_seguinte, "mes_seguinte": mes_seguinte,
        "eh_mes_atual": ano == hoje.year and mes_num == hoje.month,
    })


@login_required
def ano(request):
    hoje = timezone.localdate()
    try:
        ano_num = int(request.GET.get("ano", hoje.year))
        date(ano_num, 1, 1)
    except (TypeError, ValueError, OverflowError):
        ano_num = hoje.year

    por_mes = motor.contagem_por_mes_do_ano(ano_num)
    meses = [
        {
            "numero": m,
            "referencia": date(ano_num, m, 1),
            "qtd": por_mes[m],
            "atual": ano_num == hoje.year and m == hoje.month,
        }
        for m in range(1, 13)
    ]

    return render(request, "agenda/ano.html", {
        "aba": "agenda",
        "ano": ano_num,
        "meses": meses,
        "total_ano": sum(por_mes.values()),
        "ano_anterior": ano_num - 1,
        "ano_seguinte": ano_num + 1,
        "eh_ano_atual": ano_num == hoje.year,
    })
