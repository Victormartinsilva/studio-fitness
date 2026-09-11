from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.cadastros.models import Aluno, Equipamento, Professor, TipoSessao
from apps.contas.models import Usuario

from . import servicos
from .models import DisponibilidadeProfessor


def _horario(dia, hora, minuto=0):
    """Próxima data futura no dia da semana pedido (0=segunda), no horário informado."""
    hoje = timezone.localdate()
    delta = (dia - hoje.weekday()) % 7
    delta = delta or 7
    data = hoje + timedelta(days=delta)
    return timezone.make_aware(datetime.combine(data, datetime.min.time()) + timedelta(hours=hora, minutes=minuto))


class RegrasDeAgendaTests(TestCase):
    def setUp(self):
        self.tipo = TipoSessao.objects.create(
            nome="EMS", duracao_min=45, preparo_min=20, troca_min=15, professor_no_preparo=True
        )
        usuario = Usuario.objects.create_user("bia", papel=Usuario.Papel.PROFESSOR)
        self.professor = Professor.objects.create(usuario=usuario)
        self.professor.tipos_habilitados.add(self.tipo)
        self.aluno = Aluno.objects.create(nome="Mariana")
        self.equipamento = Equipamento.objects.create(nome="Equip. 01")
        self.inicio = _horario(dia=0, hora=10)  # segunda-feira
        self.fim = self.inicio + timedelta(minutes=self.tipo.duracao_min)

    def test_agenda_sessao_valida(self):
        sessao = servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=self.equipamento, inicio=self.inicio, fim=self.fim,
        )
        self.assertEqual(sessao.reserva_inicio, self.inicio - timedelta(minutes=20))
        self.assertEqual(sessao.reserva_fim, self.fim + timedelta(minutes=15))

    def test_rejeita_professor_nao_habilitado(self):
        self.professor.tipos_habilitados.remove(self.tipo)
        with self.assertRaisesMessage(ValidationError, "não está habilitado"):
            servicos.agendar(
                professor=self.professor, aluno=self.aluno, tipo=self.tipo,
                equipamento=self.equipamento, inicio=self.inicio, fim=self.fim,
            )

    def test_rejeita_fora_da_disponibilidade_cadastrada(self):
        DisponibilidadeProfessor.objects.create(
            professor=self.professor, dia_semana=self.inicio.weekday(),
            hora_inicio="14:00", hora_fim="18:00",
        )
        with self.assertRaisesMessage(ValidationError, "não tem disponibilidade"):
            servicos.agendar(
                professor=self.professor, aluno=self.aluno, tipo=self.tipo,
                equipamento=self.equipamento, inicio=self.inicio, fim=self.fim,
            )

    def test_permite_dentro_da_disponibilidade_cadastrada(self):
        DisponibilidadeProfessor.objects.create(
            professor=self.professor, dia_semana=self.inicio.weekday(),
            hora_inicio="08:00", hora_fim="12:00",
        )
        servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=self.equipamento, inicio=self.inicio, fim=self.fim,
        )

    def test_rejeita_equipamento_em_manutencao(self):
        self.equipamento.status = Equipamento.Status.MANUTENCAO
        self.equipamento.save()
        with self.assertRaisesMessage(ValidationError, "não pode ser reservado"):
            servicos.agendar(
                professor=self.professor, aluno=self.aluno, tipo=self.tipo,
                equipamento=self.equipamento, inicio=self.inicio, fim=self.fim,
            )

    def test_rejeita_conflito_de_professor(self):
        servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=self.equipamento, inicio=self.inicio, fim=self.fim,
        )
        outro_equipamento = Equipamento.objects.create(nome="Equip. 02")
        with self.assertRaisesMessage(ValidationError, "já tem outra sessão"):
            servicos.agendar(
                professor=self.professor, aluno=self.aluno, tipo=self.tipo,
                equipamento=outro_equipamento, inicio=self.inicio + timedelta(minutes=10), fim=self.fim + timedelta(minutes=10),
            )

    def test_cancelar_libera_horario(self):
        sessao = servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=self.equipamento, inicio=self.inicio, fim=self.fim,
        )
        servicos.cancelar(sessao=sessao)
        nova = servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=self.equipamento, inicio=self.inicio, fim=self.fim,
        )
        self.assertNotEqual(sessao.pk, nova.pk)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class GradeClicavelTests(TestCase):
    """A grade deve permitir agendar clicando diretamente num horário livre."""

    def setUp(self):
        self.tipo = TipoSessao.objects.create(nome="EMS", duracao_min=45, preparo_min=10, troca_min=10)
        usuario = Usuario.objects.create_user("bia", password="teste12345", papel=Usuario.Papel.PROFESSOR)
        self.professor = Professor.objects.create(usuario=usuario)
        self.professor.tipos_habilitados.add(self.tipo)
        self.aluno = Aluno.objects.create(nome="Mariana")
        self.equipamento = Equipamento.objects.create(nome="Equip. 01")
        self.dia = timezone.localdate() + timedelta(days=1)
        self.url = reverse("agenda:grade") + f"?data={self.dia.isoformat()}"

    def test_professor_ve_vagas_clicaveis_no_dia_livre(self):
        self.client.force_login(self.professor.usuario)

        response = self.client.get(self.url)

        self.assertContains(response, "bloco livre")
        self.assertContains(response, reverse("agenda:agendar"))
        self.assertContains(response, f"equipamento={self.equipamento.id}")

    def test_horario_ocupado_nao_aparece_como_vaga(self):
        inicio = timezone.make_aware(datetime.combine(self.dia, datetime.min.time()) + timedelta(hours=10))
        fim = inicio + timedelta(minutes=self.tipo.duracao_min)
        servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=self.equipamento, inicio=inicio, fim=fim,
        )
        self.client.force_login(self.professor.usuario)

        response = self.client.get(self.url)

        self.assertContains(response, "hora_inicio=09:30")
        self.assertNotContains(response, "hora_inicio=10:00")

    def test_aluno_nao_ve_vagas_clicaveis(self):
        usuario_aluno = Usuario.objects.create_user(
            "mari", password="teste12345", papel=Usuario.Papel.ALUNO
        )
        Aluno.objects.filter(pk=self.aluno.pk).update(usuario=usuario_aluno)
        self.client.force_login(usuario_aluno)

        response = self.client.get(self.url)

        self.assertNotContains(response, "bloco livre")

    def test_clicar_na_vaga_preenche_formulario_de_agendar(self):
        self.client.force_login(self.professor.usuario)
        url = reverse("agenda:agendar") + f"?data={self.dia.isoformat()}&hora_inicio=09:30&equipamento={self.equipamento.id}"

        response = self.client.get(url)

        self.assertContains(response, 'value="09:30"')
        self.assertContains(response, f'value="{self.equipamento.id}" selected')
