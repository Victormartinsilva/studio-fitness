from django import forms

from apps.cadastros.models import Aluno, Equipamento, Professor, TipoSessao


class AgendarForm(forms.Form):
    professor = forms.ModelChoiceField(queryset=Professor.objects.filter(ativo=True))
    # A validação continua a de um `ModelChoiceField` normal (o valor
    # submetido precisa ser o ID de um aluno ativo) — só a APRESENTAÇÃO muda:
    # no template o campo real fica escondido (`<input type="hidden">`) e um
    # `<input>` de texto com `<datalist>` (busca por nome, sem `<select>`
    # nativo nem fetch) o preenche via JS. Ver `templates/agenda/agendar.html`
    # e `static/js/agenda.js`.
    aluno = forms.ModelChoiceField(
        queryset=Aluno.objects.filter(ativo=True), widget=forms.HiddenInput()
    )
    tipo = forms.ModelChoiceField(queryset=TipoSessao.objects.filter(ativo=True), label="Tipo de sessão")
    equipamento = forms.ModelChoiceField(
        queryset=Equipamento.objects.filter(status=Equipamento.Status.ATIVO),
        required=False,
    )
    data = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    hora_inicio = forms.TimeField(
        label="Hora de início", widget=forms.TimeInput(attrs={"type": "time"})
    )


class RemararForm(forms.Form):
    """Formulário minimalista para `views.remarcar`: só data/hora/equipamento
    mudam — a duração continua a do `TipoSessao` da sessão original, e
    professor/aluno/tipo não são reeditáveis aqui (para isso, cancela e
    cria uma nova sessão)."""

    data = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    hora_inicio = forms.TimeField(
        label="Hora de início", widget=forms.TimeInput(attrs={"type": "time"})
    )
    equipamento = forms.ModelChoiceField(
        queryset=Equipamento.objects.filter(status=Equipamento.Status.ATIVO),
        required=False,
    )
