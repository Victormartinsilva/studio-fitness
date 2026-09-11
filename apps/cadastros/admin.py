from django.contrib import admin

from .models import Aluno, Equipamento, Professor, TipoSessao


@admin.register(Equipamento)
class EquipamentoAdmin(admin.ModelAdmin):
    list_display = ("nome", "status")
    list_filter = ("status",)


@admin.register(TipoSessao)
class TipoSessaoAdmin(admin.ModelAdmin):
    list_display = ("nome", "duracao_min", "preparo_min", "troca_min", "requer_equipamento", "ativo")
    list_filter = ("ativo", "requer_equipamento")


@admin.register(Professor)
class ProfessorAdmin(admin.ModelAdmin):
    list_display = ("usuario", "telefone", "ativo")
    filter_horizontal = ("tipos_habilitados",)


@admin.register(Aluno)
class AlunoAdmin(admin.ModelAdmin):
    list_display = ("nome", "telefone", "email", "ativo")
    search_fields = ("nome", "email")
