from django.test import TestCase, override_settings
from django.urls import reverse

from apps.contas.models import Usuario

from .models import VisibilidadeEixo, VisibilidadeModulo


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

    def test_visoes_lista_eixos_de_navegacao_com_gestor(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("modulos:visoes"))
        self.assertContains(response, "Seções da navegação")
        self.assertContains(response, "Meus alunos")
        self.assertContains(response, "Gestor")

    def test_desmarcar_eixo_esconde_link_do_menu_para_o_perfil(self):
        self.client.force_login(self.administrador)
        # todos os checkboxes de eixo aplicáveis presentes = mantém os demais marcados;
        # deixar de enviar "eixo__gestor__alunos" desmarca esse eixo para o gestor.
        self.client.post(
            reverse("modulos:visoes"),
            {
                "eixos_enviados": "1",
                "eixo__professor__meus_alunos": "on",
                "eixo__gestor__equipamentos": "on",
                "eixo__gestor__tipos_sessao": "on",
                "eixo__gestor__planos": "on",
            },
        )
        self.assertTrue(
            VisibilidadeEixo.objects.filter(papel="gestor", slug="alunos", visivel=False).exists()
        )

        self.client.force_login(self.gestor)
        response = self.client.get(reverse("painel:home"))
        self.assertNotContains(response, 'href="/cadastros/alunos/"')
        self.assertContains(response, 'href="/cadastros/equipamentos/"')

    def test_superusuario_sempre_ve_eixos_mesmo_ocultos_para_gestor(self):
        VisibilidadeEixo.objects.create(papel="gestor", slug="alunos", visivel=False)

        self.client.force_login(self.administrador)
        response = self.client.get(reverse("painel:home"))

        self.assertContains(response, 'href="/cadastros/alunos/"')

    def test_post_sem_marcador_de_eixos_nao_altera_visibilidade_dos_eixos(self):
        self.client.force_login(self.administrador)
        self.client.post(
            reverse("modulos:visoes"),
            {"professor__financeiro": "on"},
        )
        self.assertFalse(VisibilidadeEixo.objects.exists())

    def test_nav_nao_mostra_mais_link_de_modulos(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("painel:home"))
        self.assertNotContains(response, ">Módulos<")
