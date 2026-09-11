from django.test import TestCase, override_settings
from django.urls import reverse

from apps.contas.models import Usuario


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
        self.administrador = Usuario.objects.create_superuser(
            username="adm", password="senha-segura", email="adm@example.com", papel=Usuario.Papel.GESTOR
        )

    def test_usuario_autenticado_visualiza_roadmap(self):
        self.client.force_login(self.gestor)

        response = self.client.get(reverse("modulos:indice"))

        self.assertContains(response, "Gestão financeira")
        self.assertContains(response, "Em breve")

    def test_apenas_administrador_visualiza_previa_de_modulo_bloqueado(self):
        self.client.force_login(self.gestor)
        response = self.client.get(reverse("modulos:detalhe", args=["financeiro"]))
        self.assertNotContains(response, "Prévia administrativa")

        self.client.force_login(self.administrador)
        response = self.client.get(reverse("modulos:detalhe", args=["financeiro"]))
        self.assertContains(response, "Prévia administrativa")
