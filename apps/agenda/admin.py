from django.contrib import admin

from .models import BloqueioEquipamento, DisponibilidadeProfessor, EventoSessao, Sessao


@admin.register(Sessao)
class SessaoAdmin(admin.ModelAdmin):
    list_display = ("aluno", "professor", "equipamento", "tipo", "inicio", "fim", "status")
    list_filter = ("status", "equipamento", "tipo")
    date_hierarchy = "inicio"
    search_fields = ("aluno__nome", "professor__usuario__username")


@admin.register(EventoSessao)
class EventoSessaoAdmin(admin.ModelAdmin):
    list_display = ("sessao", "acao", "usuario", "criado_em")
    list_filter = ("acao",)


@admin.register(DisponibilidadeProfessor)
class DisponibilidadeProfessorAdmin(admin.ModelAdmin):
    list_display = ("professor", "dia_semana", "hora_inicio", "hora_fim")
    list_filter = ("dia_semana",)


@admin.register(BloqueioEquipamento)
class BloqueioEquipamentoAdmin(admin.ModelAdmin):
    list_display = ("equipamento", "inicio", "fim", "motivo")
    list_filter = ("motivo",)
