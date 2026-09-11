from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    class Papel(models.TextChoices):
        GESTOR = "gestor", "Gestor"
        PROFESSOR = "professor", "Professor"
        ALUNO = "aluno", "Aluno"

    papel = models.CharField(max_length=20, choices=Papel.choices)

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"

    @property
    def is_gestor(self):
        return self.papel == self.Papel.GESTOR

    @property
    def is_professor(self):
        return self.papel == self.Papel.PROFESSOR

    @property
    def is_aluno(self):
        return self.papel == self.Papel.ALUNO
