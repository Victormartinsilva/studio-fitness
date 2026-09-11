from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.cadastros.models import Aluno
from apps.contas.models import Usuario

from .models import AvaliacaoFisica


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class AvaliacoesFisicasTests(TestCase):
    def setUp(self):
        self.gestor = Usuario.objects.create_user(
            username="gestor", password="senha-segura", papel=Usuario.Papel.GESTOR
        )
        self.aluno = Aluno.objects.create(nome="Mariana")
        self.url = reverse("avaliacoes:evolucao", args=[self.aluno.pk])

    def test_gestor_registra_avaliacao_para_aluno(self):
        self.client.force_login(self.gestor)

        response = self.client.post(
            self.url,
            {
                "data": "2026-09-11",
                "peso_kg": "62.5",
                "percentual_gordura": "24.0",
                "massa_magra_kg": "47.5",
                "braco_cm": "",
                "cintura_cm": "",
                "quadril_cm": "",
                "coxa_cm": "",
                "observacoes": "Avaliação inicial.",
            },
        )

        self.assertRedirects(response, self.url)
        avaliacao = AvaliacaoFisica.objects.get(aluno=self.aluno)
        self.assertEqual(avaliacao.data, date(2026, 9, 11))
        self.assertEqual(avaliacao.peso_kg, Decimal("62.5"))
        self.assertEqual(avaliacao.registrado_por, self.gestor)

    def test_evolucao_exibe_variacao_entre_avaliacoes(self):
        AvaliacaoFisica.objects.create(
            aluno=self.aluno, data=date(2026, 8, 11), peso_kg=Decimal("64.0")
        )
        AvaliacaoFisica.objects.create(
            aluno=self.aluno, data=date(2026, 9, 11), peso_kg=Decimal("62.5")
        )
        self.client.force_login(self.gestor)

        response = self.client.get(f"{self.url}?novo=1")

        self.assertContains(response, "62.5 kg")
        self.assertContains(response, "-1.5 kg desde a anterior")
        self.assertContains(response, "Nova avaliação")

    def test_aluno_nao_acessa_avaliacoes_de_outro_aluno(self):
        usuario = Usuario.objects.create_user(
            username="aluna", password="senha-segura", papel=Usuario.Papel.ALUNO
        )
        self.client.force_login(usuario)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)
