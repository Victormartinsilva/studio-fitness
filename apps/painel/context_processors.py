from .alertas import gerar_alertas


def alertas_topbar(request):
    if not request.user.is_authenticated:
        return {}
    return {"alertas_topbar": gerar_alertas(request.user)}
