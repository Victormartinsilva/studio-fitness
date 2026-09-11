from django.test import TestCase, override_settings
from django.urls import reverse

from apps.contas.models import Usuario

from .models import VisibilidadeModulo


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class ModulosTests(TestCase):
    def setUp(self):
        self.gestor = Usuario.objects.create_user(
            username="gestor", password="senha-segura", papel=Usuario.Papel.GESTOR
        )
        self.professor = Usuario.objects.create_user(
            username="bia", password="senha-segura", papel=Usuario.Papel.PROFESSOR
        )
        self.administrador = Usuario.objects.create_superuser(
            username="adm", password="senha-segura", email="adm@example.com", papel=Usuario.Papel.GESTOR
        )

    def test_apenas_administrador_acessa_indice_de_modulos(self):
        self.client.force_login(self.gestor)
        response = self.client.get(reverse("modulos:indice"))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.administrador)
        response = self.client.get(reverse("modulos:indice"))
        self.assertContains(response, "Gestão financeira")

    def test_apenas_administrador_acessa_detalhe_de_modulo(self):
        self.client.force_login(self.professor)
        response = self.client.get(reverse("modulos:detalhe", args=["financeiro"]))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.administrador)
        response = self.client.get(reverse("modulos:detalhe", args=["financeiro"]))
        self.assertContains(response, "Prévia administrativa")

    def test_apenas_administrador_configura_visoes(self):
        self.client.force_login(self.gestor)
        response = self.client.get(reverse("modulos:visoes"))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.administrador)
        response = self.client.post(
            reverse("modulos:visoes"),
            {"professor__financeiro": "on"},
        )
        self.assertRedirects(response, reverse("modulos:visoes"))
        self.assertTrue(
            VisibilidadeModulo.objects.filter(
                papel=Usuario.Papel.PROFESSOR, slug="financeiro", visivel=True
            ).exists()
        )
