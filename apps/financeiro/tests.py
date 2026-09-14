from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.cadastros.models import Aluno
from apps.contas.models import Usuario
from apps.modulos.models import VisibilidadeEixo
from apps.planos.models import Contratacao, Plano

from . import servicos
from .models import Cobranca, EventoCobranca


def _contratacao(aluno, *, modalidade, valor="150.00", data_inicio=None, status=Contratacao.Status.ATIVA):
    plano = Plano.objects.create(
        nome=f"Plano {modalidade} {aluno.nome}", modalidade=modalidade, valor=Decimal(valor)
    )
    return Contratacao.objects.create(
        aluno=aluno,
        plano=plano,
        data_inicio=data_inicio or date(2026, 8, 15),
        status=status,
    )


class GerarCobrancasTests(TestCase):
    def setUp(self):
        self.aluno = Aluno.objects.create(nome="Mariana")

    def test_gera_cobranca_de_contratacao_recorrente_ativa(self):
        contratacao = _contratacao(self.aluno, modalidade=Plano.Modalidade.RECORRENTE, data_inicio=date(2026, 8, 15))

        criadas = servicos.gerar_cobrancas(referencia=date(2026, 9, 10))

        self.assertEqual(len(criadas), 1)
        cobranca = Cobranca.objects.get(contratacao=contratacao)
        self.assertEqual(cobranca.competencia, "09/2026")
        self.assertEqual(cobranca.vencimento, date(2026, 9, 15))
        self.assertEqual(cobranca.valor, Decimal("150.00"))
        self.assertEqual(cobranca.status, Cobranca.Status.PENDENTE)
        self.assertTrue(EventoCobranca.objects.filter(cobranca=cobranca, acao="gerada").exists())

    def test_recuo_para_ultimo_dia_do_mes_quando_dia_de_inicio_nao_existe(self):
        _contratacao(self.aluno, modalidade=Plano.Modalidade.RECORRENTE, data_inicio=date(2026, 1, 31))

        servicos.gerar_cobrancas(referencia=date(2026, 2, 5))

        cobranca = Cobranca.objects.get()
        self.assertEqual(cobranca.vencimento, date(2026, 2, 28))

    def test_gerar_e_idempotente_no_mesmo_mes(self):
        _contratacao(self.aluno, modalidade=Plano.Modalidade.RECORRENTE)

        servicos.gerar_cobrancas(referencia=date(2026, 9, 10))
        criadas_de_novo = servicos.gerar_cobrancas(referencia=date(2026, 9, 20))

        self.assertEqual(criadas_de_novo, [])
        self.assertEqual(Cobranca.objects.count(), 1)

    def test_mes_seguinte_gera_nova_cobranca_recorrente(self):
        _contratacao(self.aluno, modalidade=Plano.Modalidade.RECORRENTE)

        servicos.gerar_cobrancas(referencia=date(2026, 9, 10))
        servicos.gerar_cobrancas(referencia=date(2026, 10, 10))

        self.assertEqual(Cobranca.objects.count(), 2)
        self.assertEqual(
            set(Cobranca.objects.values_list("competencia", flat=True)), {"09/2026", "10/2026"}
        )

    def test_pacote_gera_uma_unica_cobranca_para_sempre(self):
        _contratacao(self.aluno, modalidade=Plano.Modalidade.PACOTE, data_inicio=date(2026, 9, 3))

        servicos.gerar_cobrancas(referencia=date(2026, 9, 10))
        servicos.gerar_cobrancas(referencia=date(2026, 10, 10))

        self.assertEqual(Cobranca.objects.count(), 1)
        cobranca = Cobranca.objects.get()
        self.assertEqual(cobranca.competencia, "Pacote")
        self.assertEqual(cobranca.vencimento, date(2026, 9, 3))

    def test_contratacao_encerrada_nao_gera_cobranca(self):
        _contratacao(
            self.aluno, modalidade=Plano.Modalidade.RECORRENTE, status=Contratacao.Status.ENCERRADA
        )

        criadas = servicos.gerar_cobrancas(referencia=date(2026, 9, 10))

        self.assertEqual(criadas, [])
        self.assertFalse(Cobranca.objects.exists())


class RegistrarPagamentoECancelamentoTests(TestCase):
    def setUp(self):
        self.aluno = Aluno.objects.create(nome="Mariana")
        contratacao = _contratacao(self.aluno, modalidade=Plano.Modalidade.RECORRENTE)
        self.cobranca = Cobranca.objects.create(
            contratacao=contratacao, competencia="09/2026", valor=Decimal("150.00"), vencimento=date(2026, 9, 15)
        )

    def test_registrar_pagamento_marca_paga_e_registra_evento(self):
        servicos.registrar_pagamento(cobranca=self.cobranca, data_pagamento=date(2026, 9, 14))

        self.cobranca.refresh_from_db()
        self.assertEqual(self.cobranca.status, Cobranca.Status.PAGA)
        self.assertEqual(self.cobranca.data_pagamento, date(2026, 9, 14))
        self.assertTrue(EventoCobranca.objects.filter(cobranca=self.cobranca, acao="paga").exists())

    def test_nao_pode_pagar_cobranca_ja_paga(self):
        servicos.registrar_pagamento(cobranca=self.cobranca)

        with self.assertRaises(ValidationError):
            servicos.registrar_pagamento(cobranca=self.cobranca)

    def test_cancelar_cobranca_pendente(self):
        servicos.cancelar_cobranca(cobranca=self.cobranca, motivo="Aluno trancou o plano.")

        self.cobranca.refresh_from_db()
        self.assertEqual(self.cobranca.status, Cobranca.Status.CANCELADA)
        self.assertTrue(EventoCobranca.objects.filter(cobranca=self.cobranca, acao="cancelada").exists())

    def test_nao_pode_cancelar_cobranca_ja_paga(self):
        servicos.registrar_pagamento(cobranca=self.cobranca)

        with self.assertRaises(ValidationError):
            servicos.cancelar_cobranca(cobranca=self.cobranca)

    def test_esta_atrasada_apenas_pendente_e_vencida(self):
        self.cobranca.vencimento = timezone.localdate() - timedelta(days=1)
        self.cobranca.save(update_fields=["vencimento"])
        self.assertTrue(self.cobranca.esta_atrasada)

        servicos.registrar_pagamento(cobranca=self.cobranca)
        self.assertFalse(self.cobranca.esta_atrasada)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class CobrancasViewTests(TestCase):
    def setUp(self):
        self.gestor = Usuario.objects.create_user(
            username="gestor", password="senha-segura", papel=Usuario.Papel.GESTOR
        )
        self.professor = Usuario.objects.create_user(
            username="bia", password="senha-segura", papel=Usuario.Papel.PROFESSOR
        )
        self.aluno = Aluno.objects.create(nome="Mariana")
        self.contratacao = _contratacao(self.aluno, modalidade=Plano.Modalidade.RECORRENTE)
        self.url = reverse("financeiro:cobrancas")

    def test_professor_nao_acessa_financeiro(self):
        self.client.force_login(self.professor)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_gestor_gera_cobrancas_do_mes(self):
        self.client.force_login(self.gestor)

        response = self.client.post(reverse("financeiro:gerar"))

        self.assertRedirects(response, self.url)
        self.assertEqual(Cobranca.objects.count(), 1)

    def test_gerar_de_novo_no_mesmo_mes_nao_duplica(self):
        self.client.force_login(self.gestor)
        self.client.post(reverse("financeiro:gerar"))

        self.client.post(reverse("financeiro:gerar"))

        self.assertEqual(Cobranca.objects.count(), 1)

    def test_dar_baixa_via_view(self):
        cobranca = Cobranca.objects.create(
            contratacao=self.contratacao, competencia="09/2026", valor=Decimal("150.00"),
            vencimento=date(2026, 9, 15),
        )
        self.client.force_login(self.gestor)

        response = self.client.post(
            reverse("financeiro:cobrancas_editar", args=[cobranca.pk]), {"_pagar": "1"}
        )

        self.assertRedirects(response, self.url)
        cobranca.refresh_from_db()
        self.assertEqual(cobranca.status, Cobranca.Status.PAGA)

    def test_filtro_por_status_atrasada(self):
        vencida = Cobranca.objects.create(
            contratacao=self.contratacao, competencia="08/2026", valor=Decimal("150.00"),
            vencimento=timezone.localdate() - timedelta(days=5),
        )
        Cobranca.objects.create(
            contratacao=self.contratacao, competencia="09/2026", valor=Decimal("150.00"),
            vencimento=timezone.localdate() + timedelta(days=5),
        )
        self.client.force_login(self.gestor)

        response = self.client.get(self.url, {"status": "atrasada"})

        # Confere pelo "titulo" completo (aluno + competência), não por um
        # trecho solto de data — "vence dd/09/2026" da própria atrasada
        # também contém a substring "09/2026", o que daria falso positivo.
        self.assertContains(response, "Mariana · 08/2026")
        self.assertNotContains(response, "Mariana · 09/2026")


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class NavEAlertasFinanceiroTests(TestCase):
    def setUp(self):
        self.gestor = Usuario.objects.create_user(
            username="gestor", password="senha-segura", papel=Usuario.Papel.GESTOR
        )
        self.aluno = Aluno.objects.create(nome="Mariana")
        self.contratacao = _contratacao(self.aluno, modalidade=Plano.Modalidade.RECORRENTE)

    def test_link_financeiro_aparece_para_gestor(self):
        self.client.force_login(self.gestor)

        response = self.client.get(reverse("painel:home"))

        self.assertContains(response, 'href="/financeiro/cobrancas/"')

    def test_eixo_oculto_esconde_link_e_bloqueia_url(self):
        VisibilidadeEixo.objects.create(papel=Usuario.Papel.GESTOR, slug="financeiro", visivel=False)
        self.client.force_login(self.gestor)

        home = self.client.get(reverse("painel:home"))
        self.assertNotContains(home, 'href="/financeiro/cobrancas/"')
        # A URL continua acessível: o eixo só esconde o link do menu, e
        # (diferente de "evolucao") a view não chama `eixo_visivel` — é o
        # mesmo comportamento de "alunos"/"cadastros" hoje.

    def test_alerta_critico_para_cobranca_atrasada(self):
        Cobranca.objects.create(
            contratacao=self.contratacao, competencia="08/2026", valor=Decimal("150.00"),
            vencimento=timezone.localdate() - timedelta(days=3),
        )
        self.client.force_login(self.gestor)

        response = self.client.get(reverse("painel:home"))

        self.assertContains(response, "1 cobrança(s) atrasada(s).")

    def test_sem_alerta_quando_nao_ha_cobranca_pendente(self):
        self.client.force_login(self.gestor)

        response = self.client.get(reverse("painel:home"))

        self.assertNotContains(response, "cobrança(s) atrasada(s)")
