import json
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.agenda import servicos
from apps.cadastros.models import Aluno, Equipamento, Professor, TipoSessao
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
        # "portal-aluno" (Fase 3) usado aqui de propósito: precisa de um
        # módulo ainda não liberado pra exercitar a prévia "Em breve para
        # você" — "financeiro" já foi liberado (Fase 2 completa).
        VisibilidadeModulo.objects.create(
            papel=Usuario.Papel.PROFESSOR, slug="portal-aluno", visivel=True
        )
        self.client.force_login(self.professor)

        response = self.client.get(self.url)

        self.assertContains(response, "Em breve para você")
        self.assertContains(response, "Portal do aluno")

    def test_gestor_ve_os_4_cards_de_kpi(self):
        self.client.force_login(self.gestor)

        response = self.client.get(self.url)

        self.assertContains(response, "Ocupação hoje")
        self.assertContains(response, "Sessões hoje")
        self.assertContains(response, "Alunos ativos")
        self.assertContains(response, "Equipamentos ativos")


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class SinoDeAlertasTests(TestCase):
    """O sino de alertas mora em `base.html` (via o context processor
    `apps.painel.context_processors.alertas_topbar`), então precisa
    aparecer em QUALQUER página autenticada — não só na home."""

    def setUp(self):
        self.tipo = TipoSessao.objects.create(nome="EMS", duracao_min=45, preparo_min=10, troca_min=10)
        usuario_professor = Usuario.objects.create_user(
            "bia", password="teste12345", papel=Usuario.Papel.PROFESSOR
        )
        self.professor_usuario = usuario_professor
        self.professor = Professor.objects.create(usuario=usuario_professor)
        self.professor.tipos_habilitados.add(self.tipo)
        self.aluno = Aluno.objects.create(nome="Mariana")
        self.equipamento = Equipamento.objects.create(nome="Equip. 01")

    def test_sino_mostra_contador_com_alertas_pendentes_fora_da_home(self):
        inicio = timezone.now() + timedelta(hours=2)
        fim = inicio + timedelta(minutes=self.tipo.duracao_min)
        servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=self.equipamento, inicio=inicio, fim=fim,
        )
        self.client.force_login(self.professor_usuario)

        response = self.client.get(reverse("agenda:grade"))

        self.assertContains(response, 'class="badge-sino"')

    def test_sino_sem_badge_quando_nao_ha_alertas(self):
        self.client.force_login(self.professor_usuario)

        response = self.client.get(reverse("agenda:grade"))

        self.assertNotContains(response, 'class="badge-sino"')


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class PwaManifestTests(TestCase):
    """Etapa 4.6: manifest leve pra permitir "Adicionar à tela de início",
    sem service worker obrigatório — `base.html` só precisa linkar o
    arquivo, e o arquivo em si precisa ter os campos mínimos que o
    Lighthouse cobra pra considerar o app instalável."""

    def test_base_html_referencia_o_manifest(self):
        usuario = Usuario.objects.create_user("gestor2", password="teste12345", papel=Usuario.Papel.GESTOR)
        self.client.force_login(usuario)

        response = self.client.get(reverse("painel:home"))

        self.assertContains(response, 'rel="manifest"')

    def test_manifest_tem_campos_minimos_para_instalacao(self):
        caminho = Path(settings.BASE_DIR) / "static" / "manifest.webmanifest"
        dados = json.loads(caminho.read_text(encoding="utf-8"))

        self.assertEqual(dados["display"], "standalone")
        self.assertEqual(dados["start_url"], "/agenda/grade/#dia-atual")
        self.assertTrue(dados["name"])
        self.assertTrue(dados["short_name"])

        tamanhos = {icone["sizes"] for icone in dados["icons"]}
        self.assertIn("192x192", tamanhos)
        self.assertIn("512x512", tamanhos)
        for icone in dados["icons"]:
            self.assertTrue(
                (Path(settings.BASE_DIR) / "static" / icone["src"]).exists(),
                f"ícone {icone['src']} referenciado no manifest não existe",
            )
