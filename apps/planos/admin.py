from django.contrib import admin

from .models import Contratacao, Plano


@admin.register(Plano)
class PlanoAdmin(admin.ModelAdmin):
    list_display = ("nome", "modalidade", "sessoes_por_semana", "quantidade_sessoes", "valor", "ativo")
    list_filter = ("modalidade", "ativo")


@admin.register(Contratacao)
class ContratacaoAdmin(admin.ModelAdmin):
    list_display = ("aluno", "plano", "data_inicio", "data_fim", "status")
    list_filter = ("status", "plano")
    search_fields = ("aluno__nome",)
