import json
from datetime import datetime, timedelta
from unittest import mock

from django.core import signing
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.agenda import servicos
from apps.agenda.models import EventoSessao, Sessao
from apps.cadastros.models import Aluno, Equipamento, Professor, TipoSessao
from apps.contas.models import Usuario

from . import context_processors, ferramentas, llm
from .ferramentas import TOKEN_SALT


def _horario(dia_semana, hora, minuto=0):
    """Próxima data futura no dia da semana pedido (0=segunda), no horário informado."""
    hoje = timezone.localdate()
    delta = (dia_semana - hoje.weekday()) % 7
    delta = delta or 7
    data = hoje + timedelta(days=delta)
    return timezone.make_aware(
        datetime.combine(data, datetime.min.time()) + timedelta(hours=hora, minutes=minuto)
    )


def _mensagem_llm(texto=None, tool_calls=None):
    return {
        "choices": [
            {"message": {"role": "assistant", "content": texto, "tool_calls": tool_calls}}
        ]
    }


def _tool_call(chamada_id, nome, argumentos):
    return {
        "id": chamada_id,
        "type": "function",
        "function": {"name": nome, "arguments": json.dumps(argumentos)},
    }


@override_settings(ASSISTENTE_ATIVO=True)
class AssistenteTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.tipo = TipoSessao.objects.create(
            nome="Eletro", duracao_min=30, preparo_min=5, troca_min=5, requer_equipamento=True
        )
        self.equipamento = Equipamento.objects.create(nome="Equip. 01")

        self.usuario_gestor = Usuario.objects.create_user(
            "gestor", password="demo1234", papel=Usuario.Papel.GESTOR
        )

        self.usuario_professor = Usuario.objects.create_user(
            "bia", password="demo1234", papel=Usuario.Papel.PROFESSOR
        )
        self.professor = Professor.objects.create(usuario=self.usuario_professor, ativo=True)
        self.professor.tipos_habilitados.add(self.tipo)

        self.usuario_aluno_login = Usuario.objects.create_user(
            "mariana", password="demo1234", papel=Usuario.Papel.ALUNO
        )
        self.aluno = Aluno.objects.create(nome="Mariana", ativo=True, usuario=self.usuario_aluno_login)

        self.inicio = _horario(dia_semana=4, hora=10)  # sexta-feira 10h
        self.data_str = self.inicio.date().isoformat()
        self.hora_str = self.inicio.time().strftime("%H:%M")

    # -- fluxo de tool calls -------------------------------------------------

    @mock.patch("apps.assistente.conversa.llm.chamar")
    def test_fluxo_com_tool_call_ate_resposta_final(self, mock_chamar):
        resposta_com_tool = _mensagem_llm(
            tool_calls=[
                _tool_call(
                    "call_1",
                    "buscar_vagas",
                    {"tipo_id": self.tipo.pk, "data": self.data_str},
                )
            ]
        )
        resposta_final = _mensagem_llm(texto="Encontrei horários disponíveis para você.")
        mock_chamar.side_effect = [resposta_com_tool, resposta_final]

        self.client.login(username="bia", password="demo1234")
        resposta = self.client.post(
            reverse("assistente:mensagem"),
            data=json.dumps({"mensagem": "tem vaga hoje?"}),
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["resposta"], "Encontrei horários disponíveis para você.")
        self.assertEqual(corpo["cartoes"], [])
        self.assertEqual(mock_chamar.call_count, 2)

    @mock.patch("apps.assistente.conversa.llm.chamar")
    def test_cartao_de_proposta_de_agendamento_nao_depende_do_texto_do_modelo(self, mock_chamar):
        resposta_com_tool = _mensagem_llm(
            tool_calls=[
                _tool_call(
                    "call_1",
                    "propor_agendamento",
                    {
                        "aluno_id": self.aluno.pk,
                        "tipo_id": self.tipo.pk,
                        "professor_id": self.professor.pk,
                        "equipamento_id": self.equipamento.pk,
                        "data": self.data_str,
                        "hora": self.hora_str,
                    },
                )
            ]
        )
        resposta_final = _mensagem_llm(texto="Pronto, clique em Confirmar.")
        mock_chamar.side_effect = [resposta_com_tool, resposta_final]

        self.client.login(username="bia", password="demo1234")
        resposta = self.client.post(
            reverse("assistente:mensagem"),
            data=json.dumps({"mensagem": "agenda a Mariana sexta 10h"}),
            content_type="application/json",
        )

        corpo = resposta.json()
        self.assertEqual(len(corpo["cartoes"]), 1)
        cartao = corpo["cartoes"][0]
        self.assertTrue(cartao["disponivel"])
        self.assertIn("token", cartao)
        self.assertIn("Mariana", cartao["resumo"])
        self.assertEqual(Sessao.objects.count(), 0)

    # -- fallback entre provedores (Groq -> Gemini) --------------------------

    @override_settings(
        LLM_PROVEDORES=["groq", "gemini"],
        LLM_PROVEDORES_CONFIG={
            "groq": {
                "base_url": "https://api.groq.com/openai/v1",
                "chave": "chave-groq",
                "modelo": "modelo-groq",
            },
            "gemini": {
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "chave": "chave-gemini",
                "modelo": "modelo-gemini",
            },
        },
        LLM_TIMEOUT_S=5,
    )
    @mock.patch("httpx.post")
    def test_llm_chamar_cai_para_o_proximo_provedor_em_erro(self, mock_post):
        resposta_429 = mock.Mock(status_code=429)
        resposta_200 = mock.Mock(status_code=200)
        resposta_200.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        resposta_200.raise_for_status.return_value = None
        mock_post.side_effect = [resposta_429, resposta_200]

        resultado = llm.chamar([{"role": "user", "content": "oi"}], [])

        self.assertEqual(resultado["choices"][0]["message"]["content"], "ok")
        self.assertEqual(mock_post.call_count, 2)

    @override_settings(
        LLM_PROVEDORES=["groq", "gemini"],
        LLM_PROVEDORES_CONFIG={
            "groq": {
                "base_url": "https://api.groq.com/openai/v1",
                "chave": "chave-groq",
                "modelo": "modelo-groq",
            },
            "gemini": {
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "chave": "chave-gemini",
                "modelo": "modelo-gemini",
            },
        },
        LLM_TIMEOUT_S=5,
    )
    @mock.patch("httpx.post")
    def test_llm_chamar_levanta_erro_quando_todos_os_provedores_falham(self, mock_post):
        mock_post.return_value = mock.Mock(status_code=500)

        with self.assertRaises(llm.TodosProvedoresFalharam):
            llm.chamar([{"role": "user", "content": "oi"}], [])

        self.assertEqual(mock_post.call_count, 2)

    @mock.patch("apps.assistente.conversa.llm.chamar")
    def test_view_devolve_indisponivel_quando_llm_falha_tudo(self, mock_chamar):
        mock_chamar.side_effect = llm.TodosProvedoresFalharam("sem provedor")

        self.client.login(username="bia", password="demo1234")
        resposta = self.client.post(
            reverse("assistente:mensagem"),
            data=json.dumps({"mensagem": "oi"}),
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertIn("indisponível", corpo["resposta"])
        self.assertEqual(corpo["cartoes"], [])

    # -- permissões -----------------------------------------------------------

    def test_aluno_nao_pode_buscar_vagas(self):
        resultado = ferramentas.buscar_vagas(
            self.usuario_aluno_login, tipo_id=self.tipo.pk, data=self.data_str
        )
        self.assertEqual(resultado.get("erro"), "permissao_negada")

    def test_aluno_nao_pode_propor_agendamento(self):
        resultado = ferramentas.propor_agendamento(
            self.usuario_aluno_login,
            aluno_id=self.aluno.pk,
            tipo_id=self.tipo.pk,
            professor_id=self.professor.pk,
            equipamento_id=self.equipamento.pk,
            data=self.data_str,
            hora=self.hora_str,
        )
        self.assertEqual(resultado.get("erro"), "permissao_negada")
        self.assertEqual(Sessao.objects.count(), 0)

    def test_aluno_ve_resumo_do_dia_reduzido(self):
        resultado = ferramentas.resumo_do_dia(self.usuario_aluno_login, data=self.data_str)
        self.assertIn("ocupacao_pct", resultado)
        self.assertNotIn("por_professor", resultado)
        self.assertNotIn("por_equipamento", resultado)

    def test_gestor_ve_resumo_do_dia_completo(self):
        resultado = ferramentas.resumo_do_dia(self.usuario_gestor, data=self.data_str)
        self.assertIn("por_professor", resultado)
        self.assertIn("por_equipamento", resultado)

    # -- propor/confirmar agendamento -----------------------------------------

    def test_propor_agendamento_nao_cria_sessao(self):
        antes = Sessao.objects.count()
        resultado = ferramentas.propor_agendamento(
            self.usuario_professor,
            aluno_id=self.aluno.pk,
            tipo_id=self.tipo.pk,
            professor_id=self.professor.pk,
            equipamento_id=self.equipamento.pk,
            data=self.data_str,
            hora=self.hora_str,
        )
        self.assertTrue(resultado["disponivel"])
        self.assertIn("token", resultado)
        self.assertEqual(Sessao.objects.count(), antes)

    def test_confirmar_com_token_valido_cria_sessao(self):
        resultado = ferramentas.propor_agendamento(
            self.usuario_professor,
            aluno_id=self.aluno.pk,
            tipo_id=self.tipo.pk,
            professor_id=self.professor.pk,
            equipamento_id=self.equipamento.pk,
            data=self.data_str,
            hora=self.hora_str,
        )
        token = resultado["token"]

        self.client.login(username="bia", password="demo1234")
        resposta = self.client.post(
            reverse("assistente:confirmar"),
            data=json.dumps({"token": token}),
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertTrue(corpo["ok"])
        self.assertEqual(Sessao.objects.count(), 1)
        sessao = Sessao.objects.get()
        self.assertEqual(sessao.aluno_id, self.aluno.pk)
        evento = EventoSessao.objects.filter(sessao=sessao, acao="criada").get()
        self.assertEqual(evento.detalhe, "via assistente")

    def test_confirmar_com_token_adulterado_falha_sem_criar_sessao(self):
        resultado = ferramentas.propor_agendamento(
            self.usuario_professor,
            aluno_id=self.aluno.pk,
            tipo_id=self.tipo.pk,
            professor_id=self.professor.pk,
            equipamento_id=self.equipamento.pk,
            data=self.data_str,
            hora=self.hora_str,
        )
        token_adulterado = resultado["token"][:-1] + ("a" if resultado["token"][-1] != "a" else "b")

        self.client.login(username="bia", password="demo1234")
        resposta = self.client.post(
            reverse("assistente:confirmar"),
            data=json.dumps({"token": token_adulterado}),
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(Sessao.objects.count(), 0)

    def test_confirmar_com_token_expirado_falha_sem_criar_sessao(self):
        dados = signing.dumps(
            {
                "acao": "agendar",
                "aluno_id": self.aluno.pk,
                "tipo_id": self.tipo.pk,
                "professor_id": self.professor.pk,
                "equipamento_id": self.equipamento.pk,
                "inicio": self.inicio.isoformat(),
                "fim": (self.inicio + timedelta(minutes=self.tipo.duracao_min)).isoformat(),
                "usuario_id": self.usuario_professor.pk,
            },
            salt=TOKEN_SALT,
        )

        self.client.login(username="bia", password="demo1234")
        with mock.patch("django.core.signing.time") as mock_time:
            # Assina "agora" mas confirma como se tivesse passado bem mais
            # que os 10 minutos de validade do token.
            mock_time.time.return_value = timezone.now().timestamp() + 3600
            resposta = self.client.post(
                reverse("assistente:confirmar"),
                data=json.dumps({"token": dados}),
                content_type="application/json",
            )

        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(Sessao.objects.count(), 0)

    def test_confirmar_com_usuario_diferente_do_token_e_proibido(self):
        resultado = ferramentas.propor_agendamento(
            self.usuario_professor,
            aluno_id=self.aluno.pk,
            tipo_id=self.tipo.pk,
            professor_id=self.professor.pk,
            equipamento_id=self.equipamento.pk,
            data=self.data_str,
            hora=self.hora_str,
        )
        token = resultado["token"]

        # Loga como outro usuário (gestor), não quem gerou a proposta.
        self.client.login(username="gestor", password="demo1234")
        resposta = self.client.post(
            reverse("assistente:confirmar"),
            data=json.dumps({"token": token}),
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(Sessao.objects.count(), 0)

    def test_confirmar_com_horario_ocupado_entre_proposta_e_clique(self):
        resultado = ferramentas.propor_agendamento(
            self.usuario_professor,
            aluno_id=self.aluno.pk,
            tipo_id=self.tipo.pk,
            professor_id=self.professor.pk,
            equipamento_id=self.equipamento.pk,
            data=self.data_str,
            hora=self.hora_str,
        )
        token = resultado["token"]

        outro_aluno = Aluno.objects.create(nome="Outro Aluno", ativo=True)
        fim = self.inicio + timedelta(minutes=self.tipo.duracao_min)
        servicos.agendar(
            professor=self.professor,
            aluno=outro_aluno,
            tipo=self.tipo,
            equipamento=self.equipamento,
            inicio=self.inicio,
            fim=fim,
        )

        self.client.login(username="bia", password="demo1234")
        resposta = self.client.post(
            reverse("assistente:confirmar"),
            data=json.dumps({"token": token}),
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, 409)
        corpo = resposta.json()
        self.assertFalse(corpo["ok"])
        self.assertEqual(Sessao.objects.count(), 1)  # só a sessão do "outro aluno"

    # -- propor/confirmar cancelamento ----------------------------------------

    def test_confirmar_cancelamento_com_token_valido(self):
        fim = self.inicio + timedelta(minutes=self.tipo.duracao_min)
        sessao = servicos.agendar(
            professor=self.professor,
            aluno=self.aluno,
            tipo=self.tipo,
            equipamento=self.equipamento,
            inicio=self.inicio,
            fim=fim,
        )

        resultado = ferramentas.propor_cancelamento(
            self.usuario_professor, sessao_id=sessao.pk, justificativa="aluno remarcou"
        )
        self.assertTrue(resultado["disponivel"])

        self.client.login(username="bia", password="demo1234")
        resposta = self.client.post(
            reverse("assistente:confirmar"),
            data=json.dumps({"token": resultado["token"]}),
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, 200)
        sessao.refresh_from_db()
        self.assertEqual(sessao.status, Sessao.Status.CANCELADA)
        evento = EventoSessao.objects.filter(sessao=sessao, acao="cancelada").get()
        self.assertEqual(evento.detalhe, "via assistente")

    # -- rate limit -------------------------------------------------------------

    @override_settings(ASSISTENTE_RATE_LIMIT_MSGS=1, ASSISTENTE_RATE_LIMIT_JANELA_S=600)
    @mock.patch("apps.assistente.conversa.llm.chamar")
    def test_rate_limit_bloqueia_sem_chamar_llm(self, mock_chamar):
        mock_chamar.return_value = _mensagem_llm(texto="ok")

        self.client.login(username="bia", password="demo1234")
        primeira = self.client.post(
            reverse("assistente:mensagem"),
            data=json.dumps({"mensagem": "oi"}),
            content_type="application/json",
        )
        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(mock_chamar.call_count, 1)

        segunda = self.client.post(
            reverse("assistente:mensagem"),
            data=json.dumps({"mensagem": "oi de novo"}),
            content_type="application/json",
        )

        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(mock_chamar.call_count, 1)  # não chamou o LLM de novo
        corpo = segunda.json()
        self.assertIn("limite", corpo["resposta"])

    # -- assistente desativado --------------------------------------------------

    @override_settings(ASSISTENTE_ATIVO=False)
    def test_rota_indisponivel_quando_assistente_desativado(self):
        self.client.login(username="bia", password="demo1234")
        resposta = self.client.post(
            reverse("assistente:mensagem"),
            data=json.dumps({"mensagem": "oi"}),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 404)


# -- context processor / botão flutuante (Etapa 3b — frontend) -------------


class AssistenteContextProcessorTests(TestCase):
    def test_expoe_true_quando_settings_ativa(self):
        with override_settings(ASSISTENTE_ATIVO=True):
            contexto = context_processors.assistente_ativo(request=None)
        self.assertEqual(contexto, {"assistente_ativo": True})

    def test_expoe_false_quando_settings_desativa(self):
        with override_settings(ASSISTENTE_ATIVO=False):
            contexto = context_processors.assistente_ativo(request=None)
        self.assertEqual(contexto, {"assistente_ativo": False})


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class AssistenteBotaoFlutuanteTests(TestCase):
    """O botão/gaveta em templates/base.html só deve aparecer para usuário
    logado E com o assistente ativo — cobertura só do server-side (o JS não
    é testado aqui, não há ferramenta de browser)."""

    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            "bia", password="demo1234", papel=Usuario.Papel.PROFESSOR
        )

    @override_settings(ASSISTENTE_ATIVO=True)
    def test_botao_aparece_para_usuario_logado_com_assistente_ativo(self):
        self.client.login(username="bia", password="demo1234")
        resposta = self.client.get(reverse("painel:home"))
        self.assertContains(resposta, 'id="assistente-botao"')

    @override_settings(ASSISTENTE_ATIVO=False)
    def test_botao_nao_aparece_com_assistente_desativado(self):
        self.client.login(username="bia", password="demo1234")
        resposta = self.client.get(reverse("painel:home"))
        self.assertNotContains(resposta, 'id="assistente-botao"')

    @override_settings(ASSISTENTE_ATIVO=True)
    def test_botao_nao_aparece_para_usuario_nao_logado(self):
        resposta = self.client.get(reverse("contas:login"))
        self.assertNotContains(resposta, 'id="assistente-botao"')
