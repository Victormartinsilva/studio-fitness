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

DIA_SEMANA_INICIAL = calendar.SUNDAY  # calendários no Brasil começam no domingo


def _mes_ano_seguro(request, hoje):
    """Lê `?ano=&mes=` da querystring, com fallback pro mês atual e
    normalização de mês fora de 1..12 (navegação vira o ano)."""
    try:
        ano = int(request.GET.get("ano", hoje.year))
        mes = int(request.GET.get("mes", hoje.month))
    except (TypeError, ValueError):
        ano, mes = hoje.year, hoje.month
    ano += (mes - 1) // 12
    mes = (mes - 1) % 12 + 1
    return ano, mes


@login_required
def mes(request):
    hoje = timezone.localdate()
    ano, mes_num = _mes_ano_seguro(request, hoje)

    cal = calendar.Calendar(firstweekday=DIA_SEMANA_INICIAL)
    dias_do_mes = list(cal.itermonthdates(ano, mes_num))  # já vem em semanas completas

    contagem = motor.contagem_por_dia(dias_do_mes[0], dias_do_mes[-1])

    dias = []
    total_mes = 0
    for data_dia in dias_do_mes:
        qtd = contagem.get(data_dia, 0)
        no_mes = data_dia.month == mes_num
        if no_mes:
            total_mes += qtd
        dias.append({
            "data": data_dia,
            "no_mes": no_mes,
            "hoje": data_dia == hoje,
            "qtd": qtd,
            "nivel": motor.nivel_de_movimento(qtd),
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
