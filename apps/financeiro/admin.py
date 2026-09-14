from django.contrib import admin

from .models import Cobranca, EventoCobranca


@admin.register(Cobranca)
class CobrancaAdmin(admin.ModelAdmin):
    list_display = ("contratacao", "competencia", "valor", "vencimento", "status")
    list_filter = ("status",)
    search_fields = ("contratacao__aluno__nome",)


@admin.register(EventoCobranca)
class EventoCobrancaAdmin(admin.ModelAdmin):
    list_display = ("cobranca", "acao", "usuario", "criado_em")
    list_filter = ("acao",)
