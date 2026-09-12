from django.conf import settings
from django.db import models


class Equipamento(models.Model):
    class Status(models.TextChoices):
        ATIVO = "ativo", "Ativo"
        MANUTENCAO = "manutencao", "Em manutenção"
        INATIVO = "inativo", "Inativo"

    nome = models.CharField(max_length=60, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ATIVO)
    observacoes = models.TextField(blank=True, verbose_name="Observações")

    class Meta:
        verbose_name = "Equipamento"
        verbose_name_plural = "Equipamentos"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class TipoSessao(models.Model):
    nome = models.CharField(max_length=80, unique=True)
    duracao_min = models.PositiveSmallIntegerField(
        verbose_name="Duração (min)", help_text="Duração da sessão em minutos."
    )
    preparo_min = models.PositiveSmallIntegerField(
        default=0, help_text="Tempo de preparo do equipamento antes da sessão, em minutos."
    )
    troca_min = models.PositiveSmallIntegerField(
        default=0, help_text="Tempo de troca/higienização do equipamento depois da sessão, em minutos."
    )
    requer_equipamento = models.BooleanField(default=True)
    professor_no_preparo = models.BooleanField(
        default=False, help_text="Se marcado, o professor também fica reservado durante o preparo/troca."
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Tipo de sessão"
        verbose_name_plural = "Tipos de sessão"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    @property
    def reserva_total(self):
        return self.preparo_min + self.duracao_min + self.troca_min


class Professor(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="professor"
    )
    telefone = models.CharField(max_length=20, blank=True)
    ativo = models.BooleanField(default=True)
    tipos_habilitados = models.ManyToManyField(
        TipoSessao, related_name="professores_habilitados", blank=True
    )

    class Meta:
        verbose_name = "Professor"
        verbose_name_plural = "Professores"

    def __str__(self):
        return self.usuario.get_full_name() or self.usuario.username


class Aluno(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="aluno",
        null=True,
        blank=True,
    )
    nome = models.CharField(max_length=120)
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    observacoes = models.TextField(blank=True, verbose_name="Observações")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Aluno"
        verbose_name_plural = "Alunos"
        ordering = ["nome"]

    def __str__(self):
        return self.nome
