from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.planos.models import Contratacao


class Cobranca(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        PAGA = "paga", "Paga"
        CANCELADA = "cancelada", "Cancelada"

    contratacao = models.ForeignKey(Contratacao, on_delete=models.PROTECT, related_name="cobrancas")
    # Texto livre em vez de um campo mês/ano: cobre tanto a mensalidade
    # ("09/2026") quanto a cobrança única de pacote ("Pacote"), sem precisar
    # de dois campos ou de um null condicional.
    competencia = models.CharField(
        max_length=20, help_text='Ex.: "09/2026" para mensalidade, ou "Pacote" para cobrança única.'
    )
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    vencimento = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE)
    data_pagamento = models.DateField(null=True, blank=True)
    observacoes = models.TextField(blank=True, verbose_name="Observações")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cobrança"
        verbose_name_plural = "Cobranças"
        ordering = ["-vencimento"]

    def __str__(self):
        return f"{self.contratacao.aluno} — {self.competencia} — {self.get_status_display()}"

    @property
    def esta_atrasada(self):
        # "Atrasada" não é um status gravado — é derivado de pendente +
        # vencimento no passado. Evita precisar de um job periódico só para
        # girar o status (etapa decidiu: sem cron nesta fase).
        return self.status == self.Status.PENDENTE and self.vencimento < timezone.localdate()


class EventoCobranca(models.Model):
    cobranca = models.ForeignKey(Cobranca, on_delete=models.CASCADE, related_name="eventos")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="+", null=True, blank=True
    )
    acao = models.CharField(max_length=20, verbose_name="Ação")
    detalhe = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evento da cobrança"
        verbose_name_plural = "Eventos da cobrança"
        ordering = ["criado_em"]

    def __str__(self):
        return f"{self.acao} — cobrança {self.cobranca_id}"
