from django import forms

from .models import Cobranca


class CobrancaForm(forms.ModelForm):
    class Meta:
        model = Cobranca
        fields = ["contratacao", "competencia", "valor", "vencimento", "observacoes"]
        widgets = {"vencimento": forms.DateInput(attrs={"type": "date"})}
