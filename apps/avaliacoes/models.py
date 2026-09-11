from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.cadastros.models import Aluno


class AvaliacaoFisica(models.Model):
    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE, related_name="avaliacoes")
    data = models.DateField(default=timezone.localdate)

    peso_kg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    percentual_gordura = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    massa_magra_kg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)

    braco_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    cintura_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    quadril_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    coxa_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)

    observacoes = models.TextField(blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="+", null=True, blank=True
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Avaliação física"
        verbose_name_plural = "Avaliações físicas"
        ordering = ["-data", "-criado_em"]

    def __str__(self):
        return f"{self.aluno} — {self.data:%d/%m/%Y}"
