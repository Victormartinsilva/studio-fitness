from django import forms

from .models import Contratacao, Plano


class PlanoForm(forms.ModelForm):
    class Meta:
        model = Plano
        fields = [
            "nome",
            "modalidade",
            "sessoes_por_semana",
            "quantidade_sessoes",
            "validade_dias",
            "valor",
            "tipos_sessao",
            "ativo",
        ]
        widgets = {"tipos_sessao": forms.CheckboxSelectMultiple}


class ContratacaoForm(forms.ModelForm):
    class Meta:
        model = Contratacao
        fields = [
            "aluno",
            "plano",
            "data_inicio",
            "data_fim",
            "sessoes_contratadas",
            "sessoes_por_semana",
            "status",
        ]
        widgets = {
            "data_inicio": forms.DateInput(attrs={"type": "date"}),
            "data_fim": forms.DateInput(attrs={"type": "date"}),
        }
