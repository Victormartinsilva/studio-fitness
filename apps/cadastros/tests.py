from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.agenda import servicos
from apps.cadastros.models import Aluno, Equipamento, Professor, TipoSessao
from apps.contas.models import Usuario


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class MeusAlunosTests(TestCase):
    def setUp(self):
        self.tipo = TipoSessao.objects.create(nome="EMS", duracao_min=45, preparo_min=10, troca_min=10)
        self.equipamento = Equipamento.objects.create(nome="Equip. 01")

        usuario_bia = Usuario.objects.create_user(
            username="bia", password="teste12345", papel=Usuario.Papel.PROFESSOR
        )
        self.professor_bia = Professor.objects.create(usuario=usuario_bia)
        self.professor_bia.tipos_habilitados.add(self.tipo)

        usuario_leo = Usuario.objects.create_user(
            username="leo", password="teste12345", papel=Usuario.Papel.PROFESSOR
        )
        self.professor_leo = Professor.objects.create(usuario=usuario_leo)
        self.professor_leo.tipos_habilitados.add(self.tipo)

        self.gestor = Usuario.objects.create_user(
            username="gestor", password="teste12345", papel=Usuario.Papel.GESTOR
        )

        self.aluna_mariana = Aluno.objects.create(nome="Mariana")
        self.aluno_pedro = Aluno.objects.create(nome="Pedro")

        inicio = timezone.now() + timedelta(days=1)
        servicos.agendar(
            professor=self.professor_bia, aluno=self.aluna_mariana, tipo=self.tipo,
            equipamento=self.equipamento, inicio=inicio, fim=inicio + timedelta(minutes=self.tipo.duracao_min),
        )
        outro_inicio = timezone.now() + timedelta(days=2)
        servicos.agendar(
            professor=self.professor_leo, aluno=self.aluno_pedro, tipo=self.tipo,
            equipamento=self.equipamento, inicio=outro_inicio,
            fim=outro_inicio + timedelta(minutes=self.tipo.duracao_min),
        )

        self.url = reverse("cadastros:meus_alunos")

    def test_professor_ve_apenas_seus_proprios_alunos(self):
        self.client.force_login(self.professor_bia.usuario)

        response = self.client.get(self.url)

        self.assertContains(response, "Mariana")
        self.assertNotContains(response, "Pedro")

    def test_professor_sem_sessoes_ve_lista_vazia(self):
        usuario_felipe = Usuario.objects.create_user(
            username="felipe", password="teste12345", papel=Usuario.Papel.PROFESSOR
        )
        Professor.objects.create(usuario=usuario_felipe)
        self.client.force_login(usuario_felipe)

        response = self.client.get(self.url)

        self.assertContains(response, "Você ainda não tem sessões agendadas")

    def test_gestor_nao_acessa_pagina_de_professor(self):
        self.client.force_login(self.gestor)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_visitante_anonimo_e_redirecionado_para_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
