from django.contrib import admin

from .models import VisibilidadeModulo


@admin.register(VisibilidadeModulo)
class VisibilidadeModuloAdmin(admin.ModelAdmin):
    list_display = ("slug", "papel", "visivel")
    list_filter = ("papel", "visivel")

    # A configuração de visibilidade só deve ser feita pela área /modulos/visoes/,
    # restrita a superusuários; evita que staff com permissão de modelo no Admin
    # contorne essa restrição.
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

