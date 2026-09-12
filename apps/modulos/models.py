from django.db import models

from apps.contas.models import Usuario

from .catalogo import EIXOS, MODULOS

# Só perfis não administrativos precisam de configuração de visibilidade:
# gestor/superusuário sempre veem tudo pela área de módulos.
PAPEL_CONFIGURAVEL_CHOICES = [
    (Usuario.Papel.PROFESSOR, "Professor"),
    (Usuario.Papel.ALUNO, "Aluno"),
]

# Para os eixos de navegação (seções reais do menu), o admin pode configurar
# a visibilidade para qualquer perfil não administrativo, incluindo o gestor.
PAPEL_EIXO_CHOICES = [
    (Usuario.Papel.PROFESSOR, "Professor"),
    (Usuario.Papel.ALUNO, "Aluno"),
    (Usuario.Papel.GESTOR, "Gestor"),
]
_SLUGS_EM_DESENVOLVIMENTO = [(m.slug, m.titulo) for m in MODULOS if not m.liberado]
_SLUGS_DE_EIXOS = [(e.slug, e.rotulo) for e in EIXOS]


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


class VisibilidadeEixo(models.Model):
    """Controla, por perfil, se uma seção real da navegação (ex.: Alunos,
    Equipamentos, Planos, Meus alunos) aparece no menu. Ao contrário dos
    módulos em desenvolvimento, eixos são visíveis por padrão — só existe
    registro aqui quando o administrador decide esconder um eixo de um
    perfil que normalmente o veria."""

    papel = models.CharField(max_length=20, choices=PAPEL_EIXO_CHOICES)
    slug = models.CharField(max_length=40, choices=_SLUGS_DE_EIXOS)
    visivel = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Visibilidade de eixo"
        verbose_name_plural = "Visibilidades de eixo"
        unique_together = ("papel", "slug")

    def __str__(self):
        return f"{self.slug} — {self.get_papel_display()}: {'visível' if self.visivel else 'oculto'}"
