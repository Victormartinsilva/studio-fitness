from django.test import TestCase, override_settings
from django.urls import reverse

from apps.contas.models import Usuario
from apps.modulos.models import VisibilidadeModulo


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class PainelHomeTests(TestCase):
    def setUp(self):
        self.gestor = Usuario.objects.create_user(
            username="gestor", password="senha-segura", papel=Usuario.Papel.GESTOR
        )
        self.professor = Usuario.objects.create_user(
            username="bia", password="senha-segura", papel=Usuario.Papel.PROFESSOR
        )
        self.url = reverse("painel:home")

    def test_gestor_ve_secao_de_fases_completa(self):
        self.client.force_login(self.gestor)

        response = self.client.get(self.url)

        self.assertContains(response, "Plataforma por fases")
        self.assertNotContains(response, "Configurar visões dos usuários")

    def test_professor_nao_ve_previa_sem_liberacao_do_admin(self):
        self.client.force_login(self.professor)

        response = self.client.get(self.url)

        self.assertNotContains(response, "Plataforma por fases")
        self.assertNotContains(response, "Em breve para você")

    def test_professor_ve_previa_liberada_pelo_admin(self):
        VisibilidadeModulo.objects.create(
            papel=Usuario.Papel.PROFESSOR, slug="financeiro", visivel=True
        )
        self.client.force_login(self.professor)

        response = self.client.get(self.url)

        self.assertContains(response, "Em breve para você")
        self.assertContains(response, "Gestão financeira")
