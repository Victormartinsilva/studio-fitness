from django import forms

from .models import Aluno, Equipamento, TipoSessao


class AlunoForm(forms.ModelForm):
    class Meta:
        model = Aluno
        fields = ["nome", "telefone", "email", "observacoes", "ativo"]
        widgets = {
            # `autocomplete`/`type` corretos ajudam o teclado e o
            # preenchimento automático do celular (uso principal do app).
            "nome": forms.TextInput(attrs={"autocomplete": "name"}),
            "telefone": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }


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
