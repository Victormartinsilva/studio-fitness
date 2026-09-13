from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.cadastros.models import Aluno
from apps.contas.models import Usuario
from apps.modulos.models import VisibilidadeEixo

from . import evolucao as ev
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

        self.assertContains(response, "62,5 kg")
        self.assertContains(response, "−1,5 kg")
        self.assertContains(response, "desde a última")
        self.assertContains(response, "Nova avaliação")

    def test_aluno_nao_acessa_avaliacoes_de_outro_aluno(self):
        usuario = Usuario.objects.create_user(
            username="aluna", password="senha-segura", papel=Usuario.Papel.ALUNO
        )
        self.client.force_login(usuario)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_aluno_visualiza_a_propria_evolucao_sem_poder_alterar(self):
        usuario = Usuario.objects.create_user(
            username="mariana", password="senha-segura", papel=Usuario.Papel.ALUNO
        )
        self.aluno.usuario = usuario
        self.aluno.save()
        AvaliacaoFisica.objects.create(aluno=self.aluno, peso_kg=Decimal("62.5"))
        self.client.force_login(usuario)

        response = self.client.get(self.url)

        self.assertContains(response, "62,5 kg")
        self.assertNotContains(response, "Nova avaliação")


def _avaliacao(aluno, data, **valores):
    return AvaliacaoFisica.objects.create(
        aluno=aluno, data=data, **{campo: Decimal(str(v)) for campo, v in valores.items()}
    )


class FormatacaoEvolucaoTests(SimpleTestCase):
    def test_formata_valores_em_pt_br(self):
        self.assertEqual(ev.formatar_valor(Decimal("64.8"), ev.METRICAS["peso_kg"]), "64,8 kg")
        self.assertEqual(ev.formatar_valor(Decimal("24.1"), ev.METRICAS["percentual_gordura"]), "24,1%")
        self.assertEqual(ev.formatar_variacao(Decimal("-2.3"), ev.METRICAS["percentual_gordura"]), "−2,3 p.p.")
        self.assertEqual(ev.formatar_variacao(Decimal("0.8"), ev.METRICAS["massa_magra_kg"]), "+0,8 kg")

    def test_cor_da_variacao_respeita_direcao_de_melhora(self):
        self.assertEqual(ev.classe_variacao(Decimal("-1"), ev.METRICAS["cintura_cm"]), "melhora")
        self.assertEqual(ev.classe_variacao(Decimal("-1"), ev.METRICAS["massa_magra_kg"]), "piora")
        self.assertEqual(ev.classe_variacao(Decimal("-1"), ev.METRICAS["peso_kg"]), "neutra")
        self.assertEqual(ev.classe_variacao(Decimal("0"), ev.METRICAS["cintura_cm"]), "neutra")


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class MinhaEvolucaoTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username="mariana", password="senha-segura", papel=Usuario.Papel.ALUNO
        )
        self.aluno = Aluno.objects.create(nome="Mariana", usuario=self.usuario)
        self.url = reverse("avaliacoes:minha_evolucao")

    def test_aluno_ve_cartoes_medidas_e_grafico_da_propria_evolucao(self):
        _avaliacao(self.aluno, date(2026, 8, 10), peso_kg=66.7, percentual_gordura=26.4, massa_magra_kg=48.4, cintura_cm=73.5)
        _avaliacao(self.aluno, date(2026, 9, 10), peso_kg=64.8, percentual_gordura=24.1, massa_magra_kg=49.2, cintura_cm=72.0)
        self.client.force_login(self.usuario)

        response = self.client.get(self.url)

        self.assertContains(response, "Minha evolução")
        self.assertContains(response, "64,8 kg")
        self.assertContains(response, "24,1%")
        self.assertContains(response, "−2,3 p.p.")
        self.assertContains(response, "−1,5 cm")  # cintura na silhueta
        self.assertContains(response, "grafico-ev")
        self.assertContains(response, ">Ago<")
        self.assertContains(response, reverse("avaliacoes:minha_comparacao"))
        self.assertContains(response, 'class="ativo">Evolução</a>', html=False)

    def test_nao_mostra_avaliacao_de_outro_aluno(self):
        outro = Aluno.objects.create(nome="Pedro")
        _avaliacao(outro, date(2026, 9, 10), peso_kg=91.3)
        self.client.force_login(self.usuario)

        response = self.client.get(self.url)

        self.assertNotContains(response, "91,3")
        self.assertContains(response, "Sua evolução aparece aqui")

    def test_eixo_oculto_esconde_aba_e_bloqueia_urls(self):
        VisibilidadeEixo.objects.create(papel=Usuario.Papel.ALUNO, slug="evolucao", visivel=False)
        _avaliacao(self.aluno, date(2026, 9, 10), peso_kg=64.8)
        self.client.force_login(self.usuario)

        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get(reverse("avaliacoes:evolucao", args=[self.aluno.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("painel:home")), "minha-evolucao")

    def test_gestor_nao_tem_minha_evolucao(self):
        gestor = Usuario.objects.create_user(username="g", password="x", papel=Usuario.Papel.GESTOR)
        self.client.force_login(gestor)

        self.assertRedirects(self.client.get(self.url), reverse("painel:home"), fetch_redirect_response=False)

    def test_metrica_medida_so_numa_avaliacao_antiga_continua_aparecendo(self):
        _avaliacao(self.aluno, date(2026, 8, 10), peso_kg=66.7, cintura_cm=73.5)
        _avaliacao(self.aluno, date(2026, 9, 10), peso_kg=64.8)  # sem cintura

        indicadores = ev.indicadores_atuais(list(self.aluno.avaliacoes.all()))

        self.assertEqual(indicadores["cintura_cm"]["valor"], "73,5 cm")
        self.assertEqual(indicadores["cintura_cm"]["variacao"], "")

    def test_grafico_ignora_avaliacoes_sem_a_metrica_e_usa_meses(self):
        _avaliacao(self.aluno, date(2026, 7, 10), percentual_gordura=27.0)
        _avaliacao(self.aluno, date(2026, 8, 10), peso_kg=66.7)
        _avaliacao(self.aluno, date(2026, 9, 10), percentual_gordura=24.1)

        grafico = ev.grafico(list(self.aluno.avaliacoes.all()), "percentual_gordura")

        self.assertEqual([p["eixo"] for p in grafico["pontos"]], ["Jul", "Set"])
        self.assertIsNone(ev.grafico(list(self.aluno.avaliacoes.all()), "coxa_cm"))

    def test_home_do_aluno_mostra_resumo_da_evolucao(self):
        _avaliacao(self.aluno, date(2026, 8, 10), percentual_gordura=26.4)
        _avaliacao(self.aluno, date(2026, 9, 10), percentual_gordura=24.1)
        self.client.force_login(self.usuario)

        response = self.client.get(reverse("painel:home"))

        self.assertContains(response, "Sua evolução")
        self.assertContains(response, "−2,3 p.p.")

    def test_comparar_usa_primeira_e_ultima_por_padrao(self):
        _avaliacao(self.aluno, date(2026, 3, 10), cintura_cm=78.0)
        _avaliacao(self.aluno, date(2026, 6, 10), cintura_cm=76.4)
        _avaliacao(self.aluno, date(2026, 9, 10), cintura_cm=72.0)
        self.client.force_login(self.usuario)

        response = self.client.get(reverse("avaliacoes:minha_comparacao"))

        self.assertContains(response, "78,0 cm")
        self.assertContains(response, "−6,0 cm")

    def test_comparar_ignora_avaliacao_de_outro_aluno(self):
        _avaliacao(self.aluno, date(2026, 8, 10), peso_kg=66.7)
        _avaliacao(self.aluno, date(2026, 9, 10), peso_kg=64.8)
        de_outro = _avaliacao(Aluno.objects.create(nome="Pedro"), date(2026, 1, 10), peso_kg=91.3)
        self.client.force_login(self.usuario)

        response = self.client.get(reverse("avaliacoes:minha_comparacao"), {"de": de_outro.pk})

        self.assertNotContains(response, "91,3")
        self.assertContains(response, "66,7 kg")
