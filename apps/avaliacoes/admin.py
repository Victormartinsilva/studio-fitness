from django.contrib import admin

from .models import AvaliacaoFisica


@admin.register(AvaliacaoFisica)
class AvaliacaoFisicaAdmin(admin.ModelAdmin):
    list_display = ("aluno", "data", "peso_kg", "percentual_gordura", "massa_magra_kg")
    list_filter = ("data",)
    search_fields = ("aluno__nome",)
    autocomplete_fields = ("aluno",)
    readonly_fields = ("criado_em",)
