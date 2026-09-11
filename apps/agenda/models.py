from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.cadastros.models import Aluno, Equipamento, Professor, TipoSessao
from apps.planos.models import Contratacao


class Sessao(models.Model):
    class Status(models.TextChoices):
        AGENDADA = "agendada", "Agendada"
        CONFIRMADA = "confirmada", "Confirmada"
        REALIZADA = "realizada", "Realizada"
        CANCELADA = "cancelada", "Cancelada"
        FALTOU = "faltou", "Faltou"

    professor = models.ForeignKey(Professor, on_delete=models.PROTECT, related_name="sessoes")
    aluno = models.ForeignKey(Aluno, on_delete=models.PROTECT, related_name="sessoes")
    tipo = models.ForeignKey(TipoSessao, on_delete=models.PROTECT, related_name="sessoes")
    equipamento = models.ForeignKey(
        Equipamento, on_delete=models.SET_NULL, related_name="sessoes", null=True, blank=True
    )
    contratacao = models.ForeignKey(
        Contratacao, on_delete=models.SET_NULL, related_name="sessoes", null=True, blank=True
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="sessoes_criadas",
        null=True,
        blank=True,
    )

    # Horário real da sessão (o aluno fica com o professor/equipamento).
    inicio = models.DateTimeField()
    fim = models.DateTimeField()
    # Janela em que o equipamento fica reservado (inclui preparo/troca).
    reserva_inicio = models.DateTimeField()
    reserva_fim = models.DateTimeField()
    # Janela em que o professor fica reservado (pode incluir preparo/troca).
    prof_inicio = models.DateTimeField()
    prof_fim = models.DateTimeField()

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AGENDADA)
    encaixe_manual = models.BooleanField(default=False)
    justificativa = models.TextField(blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sessão"
        verbose_name_plural = "Sessões"
        ordering = ["inicio"]

    def __str__(self):
        return f"{self.aluno} com {self.professor} em {self.inicio:%d/%m/%Y %H:%M}"

    def clean(self):
        if self.inicio and self.fim and self.fim <= self.inicio:
            raise ValidationError("O horário de fim deve ser depois do início.")


class EventoSessao(models.Model):
    sessao = models.ForeignKey(Sessao, on_delete=models.CASCADE, related_name="eventos")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    acao = models.CharField(max_length=20)
    detalhe = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evento da sessão"
        verbose_name_plural = "Eventos da sessão"
        ordering = ["criado_em"]

    def __str__(self):
        return f"{self.acao} — sessão {self.sessao_id}"


class DisponibilidadeProfessor(models.Model):
    class DiaSemana(models.IntegerChoices):
        SEGUNDA = 0, "Segunda-feira"
        TERCA = 1, "Terça-feira"
        QUARTA = 2, "Quarta-feira"
        QUINTA = 3, "Quinta-feira"
        SEXTA = 4, "Sexta-feira"
        SABADO = 5, "Sábado"
        DOMINGO = 6, "Domingo"

    professor = models.ForeignKey(Professor, on_delete=models.CASCADE, related_name="disponibilidades")
    dia_semana = models.PositiveSmallIntegerField(choices=DiaSemana.choices)
    hora_inicio = models.TimeField()
    hora_fim = models.TimeField()

    class Meta:
        verbose_name = "Disponibilidade do professor"
        verbose_name_plural = "Disponibilidades dos professores"
        ordering = ["dia_semana", "hora_inicio"]

    def __str__(self):
        return f"{self.professor} — {self.get_dia_semana_display()} {self.hora_inicio}-{self.hora_fim}"


class BloqueioEquipamento(models.Model):
    class Motivo(models.TextChoices):
        MANUTENCAO = "manutencao", "Manutenção"
        LIMPEZA = "limpeza", "Limpeza"
        OUTRO = "outro", "Outro"

    equipamento = models.ForeignKey(Equipamento, on_delete=models.CASCADE, related_name="bloqueios")
    inicio = models.DateTimeField()
    fim = models.DateTimeField()
    motivo = models.CharField(max_length=20, choices=Motivo.choices, default=Motivo.OUTRO)
    descricao = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Bloqueio de equipamento"
        verbose_name_plural = "Bloqueios de equipamento"
        ordering = ["inicio"]

    def __str__(self):
        return f"{self.equipamento} bloqueado {self.inicio:%d/%m %H:%M}-{self.fim:%H:%M}"

