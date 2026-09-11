from django import forms

from apps.cadastros.models import Aluno, Equipamento, Professor, TipoSessao


class AgendarForm(forms.Form):
    professor = forms.ModelChoiceField(queryset=Professor.objects.filter(ativo=True))
    aluno = forms.ModelChoiceField(queryset=Aluno.objects.filter(ativo=True))
    tipo = forms.ModelChoiceField(queryset=TipoSessao.objects.filter(ativo=True), label="Tipo de sessão")
    equipamento = forms.ModelChoiceField(
        queryset=Equipamento.objects.exclude(status=Equipamento.Status.INATIVO),
        required=False,
    )
    data = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    hora_inicio = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
