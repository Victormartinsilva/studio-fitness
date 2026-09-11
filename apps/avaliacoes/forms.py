from django import forms

from .models import AvaliacaoFisica


class AvaliacaoFisicaForm(forms.ModelForm):
    class Meta:
        model = AvaliacaoFisica
        fields = [
            "data",
            "peso_kg",
            "percentual_gordura",
            "massa_magra_kg",
            "braco_cm",
            "cintura_cm",
            "quadril_cm",
            "coxa_cm",
            "observacoes",
        ]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }
