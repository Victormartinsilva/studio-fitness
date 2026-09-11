from django.db import models

from apps.contas.models import Usuario

from .catalogo import MODULOS

# Só perfis não administrativos precisam de configuração de visibilidade:
# gestor/superusuário sempre veem tudo pela área de módulos.
PAPEL_CONFIGURAVEL_CHOICES = [
    (Usuario.Papel.PROFESSOR, "Professor"),
    (Usuario.Papel.ALUNO, "Aluno"),
]
_SLUGS_EM_DESENVOLVIMENTO = [(m.slug, m.titulo) for m in MODULOS if not m.liberado]


class VisibilidadeModulo(models.Model):
    """Controla, por perfil, quais módulos ainda em desenvolvimento aparecem
    como prévia ("em breve") no painel do usuário. Configurável apenas pelo
    administrador (superusuário) em /modulos/visoes/."""

    papel = models.CharField(max_length=20, choices=PAPEL_CONFIGURAVEL_CHOICES)
    slug = models.CharField(max_length=40, choices=_SLUGS_EM_DESENVOLVIMENTO)
    visivel = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Visibilidade de módulo"
        verbose_name_plural = "Visibilidades de módulo"
        unique_together = ("papel", "slug")

    def __str__(self):
        return f"{self.slug} — {self.get_papel_display()}: {'visível' if self.visivel else 'oculto'}"
