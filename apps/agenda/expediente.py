"""
Fonte única de verdade para o expediente do estúdio (horário de abertura e
de fechamento), lida das settings `AGENDA_ABERTURA_HORA` / `AGENDA_FECHAMENTO_HORA`
(default 7h–21h, mesmo padrão hoje hardcoded em `motor.py`, `grade.py` e
`painel/views.py`).

Por ora só `apps/agenda/motor.py` usa este módulo. `apps/agenda/grade.py`
(constantes `HORA_INICIO`/`HORA_FIM`) e `apps/painel/views.py` (`14 * 60`
hardcoded) continuam com suas próprias constantes — migrá-los para usar esta
fonte única é tarefa de uma etapa futura, para não arriscar regressão na
grade/painel nesta etapa.
"""
from datetime import time

from django.conf import settings

ABERTURA_HORA = getattr(settings, "AGENDA_ABERTURA_HORA", 7)
FECHAMENTO_HORA = getattr(settings, "AGENDA_FECHAMENTO_HORA", 21)

ABERTURA = time(ABERTURA_HORA, 0)
FECHAMENTO = time(FECHAMENTO_HORA, 0)

# Minutos de expediente num dia (usado para cálculos de capacidade/ocupação).
MINUTOS_EXPEDIENTE = (FECHAMENTO_HORA - ABERTURA_HORA) * 60
