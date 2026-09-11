"""
Decorador de permissão: só gestores (ou superusuários) acessam telas de
cadastro/administração da agenda.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def gestor_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.is_gestor):
            raise PermissionDenied("Apenas o gestor pode acessar esta página.")
        return view_func(request, *args, **kwargs)

    return wrapper


def admin_required(view_func):
    """Restringe a área administrativa (ex.: roadmap de módulos) ao superusuário."""

    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied("Apenas o administrador pode acessar esta página.")
        return view_func(request, *args, **kwargs)

    return wrapper
