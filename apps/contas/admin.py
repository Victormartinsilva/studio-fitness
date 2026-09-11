from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "papel", "is_staff", "is_active")
    list_filter = ("papel", "is_staff", "is_active")
    fieldsets = UserAdmin.fieldsets + (("Studio Fitness", {"fields": ("papel",)}),)
