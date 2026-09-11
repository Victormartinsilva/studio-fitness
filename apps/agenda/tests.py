from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
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
