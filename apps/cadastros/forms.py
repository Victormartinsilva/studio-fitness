from django import forms

from .models import Aluno, Equipamento, TipoSessao


class AlunoForm(forms.ModelForm):
    class Meta:
        model = Aluno
        fields = ["nome", "telefone", "email", "observacoes", "ativo"]


class EquipamentoForm(forms.ModelForm):
    class Meta:
        model = Equipamento
        fields = ["nome", "status", "observacoes"]


class TipoSessaoForm(forms.ModelForm):
    class Meta:
        model = TipoSessao
        fields = [
            "nome",
            "duracao_min",
            "preparo_min",
            "troca_min",
            "requer_equipamento",
            "professor_no_preparo",
            "ativo",
        ]
