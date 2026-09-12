from django.db import models

from apps.cadastros.models import Aluno, TipoSessao


class Plano(models.Model):
    class Modalidade(models.TextChoices):
        RECORRENTE = "recorrente", "Recorrente (por semana)"
        PACOTE = "pacote", "Pacote de sessões"

    nome = models.CharField(max_length=80, unique=True)
    modalidade = models.CharField(max_length=20, choices=Modalidade.choices)
    sessoes_por_semana = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Sessões por semana"
    )
    quantidade_sessoes = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Quantidade de sessões"
    )
    validade_dias = models.PositiveSmallIntegerField(null=True, blank=True)
    valor = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    ativo = models.BooleanField(default=True)
    tipos_sessao = models.ManyToManyField(
        TipoSessao, related_name="planos", blank=True, verbose_name="Tipos de sessão"
    )

    class Meta:
        verbose_name = "Plano"
        verbose_name_plural = "Planos"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Contratacao(models.Model):
    class Status(models.TextChoices):
        ATIVA = "ativa", "Ativa"
        ENCERRADA = "encerrada", "Encerrada"
        SUSPENSA = "suspensa", "Suspensa"

    aluno = models.ForeignKey(Aluno, on_delete=models.PROTECT, related_name="contratacoes")
    plano = models.ForeignKey(Plano, on_delete=models.PROTECT, related_name="contratacoes")
    data_inicio = models.DateField(verbose_name="Data de início")
    data_fim = models.DateField(null=True, blank=True)
    sessoes_contratadas = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Sessões contratadas"
    )
    sessoes_por_semana = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Sessões por semana"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ATIVA)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Plano assinado"
        verbose_name_plural = "Planos assinados"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.aluno} — {self.plano}"
