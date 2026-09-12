from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.cadastros.models import Aluno, Equipamento, Professor, TipoSessao
from apps.contas.models import Usuario

from . import expediente, grade as grade_modulo, motor, servicos
from .models import BloqueioEquipamento, DisponibilidadeProfessor, Sessao


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

    def test_rejeita_conflito_de_aluno(self):
        servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=self.equipamento, inicio=self.inicio, fim=self.fim,
        )
        outro_usuario = Usuario.objects.create_user("leo", papel=Usuario.Papel.PROFESSOR)
        outro_professor = Professor.objects.create(usuario=outro_usuario)
        outro_professor.tipos_habilitados.add(self.tipo)
        outro_equipamento = Equipamento.objects.create(nome="Equip. 02")

        # mesmo aluno, professor e equipamento diferentes: só o conflito do
        # aluno deve derrubar o agendamento.
        with self.assertRaisesMessage(ValidationError, f"{self.aluno} já tem outra sessão"):
            servicos.agendar(
                professor=outro_professor, aluno=self.aluno, tipo=self.tipo,
                equipamento=outro_equipamento,
                inicio=self.inicio + timedelta(minutes=10), fim=self.fim + timedelta(minutes=10),
            )

    def test_rejeita_sem_equipamento_quando_tipo_exige(self):
        tipo_exige = TipoSessao.objects.create(nome="Avaliação", duracao_min=30, requer_equipamento=True)
        self.professor.tipos_habilitados.add(tipo_exige)
        fim = self.inicio + timedelta(minutes=30)

        with self.assertRaisesMessage(ValidationError, "exige um equipamento"):
            servicos.agendar(
                professor=self.professor, aluno=self.aluno, tipo=tipo_exige,
                equipamento=None, inicio=self.inicio, fim=fim,
            )

    def test_permite_com_equipamento_quando_tipo_exige(self):
        tipo_exige = TipoSessao.objects.create(nome="Avaliação", duracao_min=30, requer_equipamento=True)
        self.professor.tipos_habilitados.add(tipo_exige)
        fim = self.inicio + timedelta(minutes=30)

        sessao = servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=tipo_exige,
            equipamento=self.equipamento, inicio=self.inicio, fim=fim,
        )

        self.assertEqual(sessao.equipamento, self.equipamento)

    def test_rejeita_professor_inativo(self):
        self.professor.ativo = False
        self.professor.save()

        with self.assertRaisesMessage(ValidationError, "não está ativo"):
            servicos.agendar(
                professor=self.professor, aluno=self.aluno, tipo=self.tipo,
                equipamento=self.equipamento, inicio=self.inicio, fim=self.fim,
            )

    def test_select_for_update_nao_quebra_no_sqlite(self):
        sessao = servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=self.equipamento, inicio=self.inicio, fim=self.fim,
        )

        remarcada = servicos.remarcar(
            sessao=sessao,
            inicio=self.inicio + timedelta(hours=1),
            fim=self.fim + timedelta(hours=1),
        )

        self.assertEqual(remarcada.pk, sessao.pk)


class BuscarVagasTests(TestCase):
    """`buscar_vagas` varre vários professores quando nenhum é fixado."""

    def setUp(self):
        self.tipo = TipoSessao.objects.create(nome="EMS", duracao_min=45, preparo_min=10, troca_min=10)
        usuario_a = Usuario.objects.create_user("bia", papel=Usuario.Papel.PROFESSOR)
        usuario_b = Usuario.objects.create_user("leo", papel=Usuario.Papel.PROFESSOR)
        self.professor_a = Professor.objects.create(usuario=usuario_a)
        self.professor_b = Professor.objects.create(usuario=usuario_b)
        self.professor_a.tipos_habilitados.add(self.tipo)
        self.professor_b.tipos_habilitados.add(self.tipo)
        self.aluno = Aluno.objects.create(nome="Mariana")
        self.equipamento = Equipamento.objects.create(nome="Equip. 01")
        self.dia = timezone.localdate() + timedelta(days=1)

    def _ocupa_professor_o_dia_todo(self, professor):
        """Cria uma sessão "guarda-chuva" que cobre todo o expediente do dia
        para o professor, simulando uma agenda cheia sem depender dos
        detalhes de `servicos.agendar`."""
        equipamento_bloqueio = Equipamento.objects.create(nome=f"Bloqueio {professor.pk}")
        inicio = timezone.make_aware(datetime.combine(self.dia, expediente.ABERTURA))
        fim = timezone.make_aware(datetime.combine(self.dia, expediente.FECHAMENTO))
        Sessao.objects.create(
            professor=professor, aluno=self.aluno, tipo=self.tipo, equipamento=equipamento_bloqueio,
            inicio=inicio, fim=fim, reserva_inicio=inicio, reserva_fim=fim,
            prof_inicio=inicio, prof_fim=fim, status=Sessao.Status.AGENDADA,
        )

    def test_sem_professor_fixado_escolhe_outro_professor_quando_o_preferido_esta_ocupado(self):
        self._ocupa_professor_o_dia_todo(self.professor_a)

        vagas = motor.buscar_vagas(tipo_sessao=self.tipo, dia=self.dia)

        self.assertTrue(vagas)
        professores_nas_vagas = {v["professor"].pk for v in vagas}
        self.assertNotIn(self.professor_a.pk, professores_nas_vagas)
        self.assertIn(self.professor_b.pk, professores_nas_vagas)

    def test_com_professor_fixado_nao_varre_outros(self):
        self._ocupa_professor_o_dia_todo(self.professor_a)

        vagas = motor.buscar_vagas(tipo_sessao=self.tipo, dia=self.dia, professor=self.professor_a)

        self.assertEqual(vagas, [])


class ResumoDoDiaTests(TestCase):
    def setUp(self):
        self.tipo = TipoSessao.objects.create(nome="EMS", duracao_min=45, preparo_min=10, troca_min=10)
        usuario = Usuario.objects.create_user("bia", papel=Usuario.Papel.PROFESSOR)
        self.professor = Professor.objects.create(usuario=usuario)
        self.professor.tipos_habilitados.add(self.tipo)
        self.aluno = Aluno.objects.create(nome="Mariana")
        self.equipamento = Equipamento.objects.create(nome="Equip. 01")
        self.equipamento_manutencao = Equipamento.objects.create(
            nome="Equip. 02", status=Equipamento.Status.MANUTENCAO
        )
        self.dia = timezone.localdate() + timedelta(days=1)
        self.inicio = timezone.make_aware(
            datetime.combine(self.dia, datetime.min.time()) + timedelta(hours=10)
        )
        self.fim = self.inicio + timedelta(minutes=self.tipo.duracao_min)

    def _minutos_reservados_da_sessao(self):
        return (
            (self.fim + timedelta(minutes=self.tipo.troca_min))
            - (self.inicio - timedelta(minutes=self.tipo.preparo_min))
        ).total_seconds() / 60

    def test_desconta_bloqueio_da_capacidade_do_equipamento(self):
        servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=self.equipamento, inicio=self.inicio, fim=self.fim,
        )
        bloqueio_inicio = timezone.make_aware(
            datetime.combine(self.dia, datetime.min.time()) + timedelta(hours=15)
        )
        BloqueioEquipamento.objects.create(
            equipamento=self.equipamento, inicio=bloqueio_inicio, fim=bloqueio_inicio + timedelta(hours=4),
        )

        resumo = motor.resumo_do_dia(self.dia)

        reservados_min = self._minutos_reservados_da_sessao()
        capacidade_com_bloqueio = expediente.MINUTOS_EXPEDIENTE - 240
        pct_esperado = round(reservados_min / capacidade_com_bloqueio * 100)
        pct_sem_bloqueio = round(reservados_min / expediente.MINUTOS_EXPEDIENTE * 100)

        self.assertEqual(resumo["por_equipamento"]["Equip. 01"]["ocupacao_pct"], pct_esperado)
        self.assertGreater(pct_esperado, pct_sem_bloqueio)

    def test_equipamento_em_manutencao_nao_conta_na_capacidade(self):
        servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=self.equipamento, inicio=self.inicio, fim=self.fim,
        )

        resumo = motor.resumo_do_dia(self.dia)

        self.assertNotIn("Equip. 02", resumo["por_equipamento"])
        reservados_min = self._minutos_reservados_da_sessao()
        pct_esperado = round(reservados_min / expediente.MINUTOS_EXPEDIENTE * 100)
        self.assertEqual(resumo["ocupacao_pct"], pct_esperado)


class ContagemPorDiaTests(TestCase):
    def setUp(self):
        self.tipo = TipoSessao.objects.create(nome="EMS", duracao_min=45)
        usuario = Usuario.objects.create_user("bia", papel=Usuario.Papel.PROFESSOR)
        self.professor = Professor.objects.create(usuario=usuario)
        self.professor.tipos_habilitados.add(self.tipo)
        self.aluno = Aluno.objects.create(nome="Mariana")
        self.equipamento = Equipamento.objects.create(nome="Equip. 01")

    def test_ignora_cancelada_e_respeita_fuso_horario_perto_da_meia_noite(self):
        dia = timezone.localdate() + timedelta(days=2)
        outro_dia = dia + timedelta(days=1)

        # sessão às 23h30 no horário de São Paulo: em UTC já é madrugada do
        # dia seguinte — precisa continuar contando para `dia`, não para
        # `outro_dia`, se o fuso horário estiver correto.
        inicio_23h30 = timezone.make_aware(
            datetime.combine(dia, datetime.min.time()) + timedelta(hours=23, minutes=30)
        )
        servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=self.equipamento, inicio=inicio_23h30, fim=inicio_23h30 + timedelta(minutes=45),
        )

        inicio_cancelada = timezone.make_aware(
            datetime.combine(outro_dia, datetime.min.time()) + timedelta(hours=10)
        )
        sessao_cancelada = servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=self.equipamento, inicio=inicio_cancelada, fim=inicio_cancelada + timedelta(minutes=45),
        )
        servicos.cancelar(sessao=sessao_cancelada)

        contagem = motor.contagem_por_dia(dia, outro_dia)

        self.assertEqual(contagem.get(dia), 1)
        self.assertNotIn(outro_dia, contagem)


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


class VagasLivresAlturaMinimaTests(TestCase):
    """`_vagas_livres` deve garantir uma altura visual mínima (~40px, alvo
    de toque) pro bloco "vaga livre", sem nunca ultrapassar o fim real do
    gap nem sobrepor o próximo slot dentro do mesmo gap."""

    def setUp(self):
        self.dia = timezone.localdate() + timedelta(days=1)
        self.agora = timezone.now()
        self.limite = (grade_modulo.HORA_FIM - grade_modulo.HORA_INICIO) * 60

    def test_slot_unico_com_folga_cresce_ate_o_fim_do_gap_sem_ultrapassar(self):
        # Ocupado a partir do minuto 32 até o fim do expediente -> só resta
        # um gap de 32min (0 a 32): um slot de 30min (36px) mais 2min de
        # folga, que devem virar altura extra sem passar de 32min (38.4px).
        vagas = grade_modulo._vagas_livres([(32, self.limite)], self.dia, 1, self.agora)

        self.assertEqual(len(vagas), 1)
        self.assertEqual(vagas[0]["top"], "0.0")
        altura_maxima_do_gap = 32 * grade_modulo.PX_POR_MIN
        self.assertEqual(vagas[0]["altura"], "{:.1f}".format(altura_maxima_do_gap))
        self.assertLess(float(vagas[0]["altura"]), grade_modulo.ALTURA_MIN_VAGA_PX)

    def test_slots_intermediarios_de_um_gap_maior_nao_se_sobrepoem(self):
        # Gap de 50min (0 a 50) -> dois slots (30min + 20min). O primeiro
        # não pode crescer (tem vizinho colado embaixo); só o último, que
        # encosta no fim real do gap, pode.
        vagas = grade_modulo._vagas_livres([(50, self.limite)], self.dia, 1, self.agora)

        self.assertEqual(len(vagas), 2)
        primeiro, segundo = vagas
        self.assertEqual(primeiro["top"], "0.0")
        self.assertEqual(primeiro["altura"], "{:.1f}".format(30 * grade_modulo.PX_POR_MIN))
        self.assertEqual(segundo["top"], "{:.1f}".format(30 * grade_modulo.PX_POR_MIN))
        self.assertEqual(segundo["altura"], "{:.1f}".format(20 * grade_modulo.PX_POR_MIN))
        # fim do primeiro bloco (top + altura) não passa do início do segundo.
        fim_primeiro = float(primeiro["top"]) + float(primeiro["altura"])
        self.assertLessEqual(fim_primeiro, float(segundo["top"]))
        # fim do segundo bloco não passa do fim real do gap.
        fim_segundo = float(segundo["top"]) + float(segundo["altura"])
        self.assertLessEqual(fim_segundo, 50 * grade_modulo.PX_POR_MIN + 1e-6)


class SugerirHorariosTests(TestCase):
    """Agenda inteligente: quando o horário/equipamento pedido não serve,
    o motor deve sugerir alternativas livres para o mesmo professor/tipo."""

    def setUp(self):
        self.tipo = TipoSessao.objects.create(nome="EMS", duracao_min=45, preparo_min=10, troca_min=10)
        usuario = Usuario.objects.create_user("bia", "senha123", papel=Usuario.Papel.PROFESSOR)
        self.professor = Professor.objects.create(usuario=usuario)
        self.professor.tipos_habilitados.add(self.tipo)
        self.aluno = Aluno.objects.create(nome="Mariana")
        self.equipamento_1 = Equipamento.objects.create(nome="Equip. 01")
        self.equipamento_2 = Equipamento.objects.create(nome="Equip. 02")
        self.dia = timezone.localdate() + timedelta(days=1)

    def test_sem_habilitacao_nao_ha_sugestoes(self):
        self.professor.tipos_habilitados.remove(self.tipo)

        sugestoes = motor.sugerir_horarios(
            professor=self.professor, tipo_sessao=self.tipo, dia=self.dia,
        )

        self.assertEqual(sugestoes, [])

    def test_sugere_outro_equipamento_livre_quando_o_preferido_esta_ocupado(self):
        inicio = timezone.make_aware(datetime.combine(self.dia, datetime.min.time()) + timedelta(hours=10))
        fim = inicio + timedelta(minutes=self.tipo.duracao_min)
        servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=self.equipamento_1, inicio=inicio, fim=fim,
        )

        sugestoes = motor.sugerir_horarios(
            professor=self.professor, tipo_sessao=self.tipo, dia=self.dia,
            equipamento_preferido=self.equipamento_1, hora_desejada=inicio.time(),
        )

        equipamentos_sugeridos = {s["equipamento"].id for s in sugestoes}
        # o professor está ocupado às 10h (mesmo em outro equipamento), então
        # nenhuma sugestão pode cair exatamente nesse horário
        for sugestao in sugestoes:
            self.assertFalse(sugestao["inicio"] <= inicio < sugestao["fim"])
        self.assertIn(self.equipamento_2.id, equipamentos_sugeridos)

    def test_sugestoes_respeitam_limite(self):
        sugestoes = motor.sugerir_horarios(
            professor=self.professor, tipo_sessao=self.tipo, dia=self.dia, limite=1,
        )

        self.assertEqual(len(sugestoes), 1)

    def test_sugestoes_nao_incluem_horario_passado(self):
        hoje = timezone.localdate()

        sugestoes = motor.sugerir_horarios(
            professor=self.professor, tipo_sessao=self.tipo, dia=hoje,
        )

        agora = timezone.now()
        for sugestao in sugestoes:
            self.assertGreaterEqual(sugestao["inicio"], agora)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class GradeInteligenteTests(TestCase):
    """Etapa 2: faixa de dias com contagem, ocupação correta (descontando
    manutenção) e filtro por professor na grade."""

    def setUp(self):
        self.tipo = TipoSessao.objects.create(nome="EMS", duracao_min=45, preparo_min=10, troca_min=10)
        usuario_gestor = Usuario.objects.create_user(
            "gestor", password="teste12345", papel=Usuario.Papel.GESTOR
        )
        self.gestor = usuario_gestor
        usuario_a = Usuario.objects.create_user("bia", password="teste12345", papel=Usuario.Papel.PROFESSOR)
        usuario_b = Usuario.objects.create_user("leo", password="teste12345", papel=Usuario.Papel.PROFESSOR)
        self.professor_a = Professor.objects.create(usuario=usuario_a)
        self.professor_b = Professor.objects.create(usuario=usuario_b)
        self.professor_a.tipos_habilitados.add(self.tipo)
        self.professor_b.tipos_habilitados.add(self.tipo)
        self.aluno = Aluno.objects.create(nome="Mariana")
        self.equipamento = Equipamento.objects.create(nome="Equip. 01")
        self.dia = timezone.localdate() + timedelta(days=1)

    def _agenda(self, professor, hora, equipamento=None):
        inicio = timezone.make_aware(
            datetime.combine(self.dia, datetime.min.time()) + timedelta(hours=hora)
        )
        fim = inicio + timedelta(minutes=self.tipo.duracao_min)
        return servicos.agendar(
            professor=professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=equipamento or self.equipamento, inicio=inicio, fim=fim,
        )

    def test_faixa_de_dias_mostra_contagem_do_dia(self):
        self._agenda(self.professor_a, hora=10)
        self._agenda(self.professor_b, hora=12, equipamento=Equipamento.objects.create(nome="Equip. 02"))
        self.client.force_login(self.gestor)

        url = reverse("agenda:grade") + f"?data={self.dia.isoformat()}"
        response = self.client.get(url)

        self.assertContains(response, '<span class="badge-dia">2</span>')

    def test_equipamento_em_manutencao_nao_conta_na_ocupacao_da_grade(self):
        self._agenda(self.professor_a, hora=10)
        equipamento_manutencao = Equipamento.objects.create(
            nome="Equip. 02", status=Equipamento.Status.MANUTENCAO
        )
        self.client.force_login(self.gestor)

        url = reverse("agenda:grade") + f"?data={self.dia.isoformat()}"
        response = self.client.get(url)

        resumo_direto = motor.resumo_do_dia(self.dia)
        self.assertNotIn("Equip. 02", resumo_direto["por_equipamento"])
        # a coluna do equipamento em manutenção continua aparecendo...
        self.assertContains(response, "Equip. 02")
        # ...mas com a etiqueta de status, não contando sessões/ocupação.
        self.assertNotContains(response, "0 sessões · 0%")

    def test_filtro_por_professor_destaca_sessoes_do_professor_e_marca_as_demais_como_outra(self):
        self._agenda(self.professor_a, hora=10)
        self._agenda(self.professor_b, hora=14, equipamento=Equipamento.objects.create(nome="Equip. 02"))
        self.client.force_login(self.gestor)

        url = reverse("agenda:grade") + f"?data={self.dia.isoformat()}&professor={self.professor_a.id}"
        response = self.client.get(url)

        self.assertContains(response, "sessao propria")
        self.assertContains(response, "sessao outra")

    def test_sem_filtro_por_professor_gestor_nao_ve_classe_outra(self):
        self._agenda(self.professor_a, hora=10)
        self._agenda(self.professor_b, hora=14, equipamento=Equipamento.objects.create(nome="Equip. 02"))
        self.client.force_login(self.gestor)

        url = reverse("agenda:grade") + f"?data={self.dia.isoformat()}"
        response = self.client.get(url)

        self.assertNotContains(response, "sessao outra")

    def test_equipamento_em_manutencao_aparece_depois_dos_ativos_na_ordem_das_colunas(self):
        # Nome propositalmente "menor" (viria primeiro em ordenação
        # alfabética) pra garantir que quem manda é o status, não o nome.
        equipamento_manutencao = Equipamento.objects.create(
            nome="Equip. 00", status=Equipamento.Status.MANUTENCAO
        )
        self.client.force_login(self.gestor)

        url = reverse("agenda:grade") + f"?data={self.dia.isoformat()}"
        response = self.client.get(url)

        equipamentos_na_ordem = [coluna["equipamento"] for coluna in response.context["colunas"]]
        self.assertEqual(equipamentos_na_ordem, [self.equipamento, equipamento_manutencao])

    def test_scroll_inicial_top_aponta_para_o_primeiro_bloco_ocupado_quando_nao_e_hoje(self):
        # `self.dia` é sempre amanhã (ver setUp), então nunca mostra a
        # "linha do agora" — o fallback precisa apontar pro início da
        # reserva do equipamento (que já inclui o preparo), não pro início
        # da sessão em si.
        sessao = self._agenda(self.professor_a, hora=10)
        self.client.force_login(self.gestor)

        url = reverse("agenda:grade") + f"?data={self.dia.isoformat()}"
        response = self.client.get(url)

        self.assertFalse(response.context["mostrar_linha_agora"])
        reserva_inicio_local = timezone.localtime(sessao.reserva_inicio)
        minutos_esperados = (
            (reserva_inicio_local.hour - grade_modulo.HORA_INICIO) * 60 + reserva_inicio_local.minute
        )
        esperado = "{:.1f}".format(minutos_esperados * grade_modulo.PX_POR_MIN)
        self.assertEqual(response.context["scroll_inicial_top"], esperado)
        self.assertContains(response, f'data-scroll-inicial-top="{esperado}"')

    def test_scroll_inicial_top_vazio_quando_dia_sem_nenhuma_sessao_ou_bloqueio(self):
        self.client.force_login(self.gestor)

        url = reverse("agenda:grade") + f"?data={self.dia.isoformat()}"
        response = self.client.get(url)

        self.assertIsNone(response.context["scroll_inicial_top"])


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class PainelEGradeOcupacaoTests(TestCase):
    """Bug original: painel e grade calculavam ocupação de formas diferentes.
    Hoje a grade não exibe mais nenhuma métrica de ocupação (essa
    informação ficou só nos cards do painel — ver
    `templates/painel/home.html`), então o teste de paridade passou a
    verificar o painel diretamente contra `motor.resumo_do_dia`, única
    fonte da verdade."""

    def setUp(self):
        self.tipo = TipoSessao.objects.create(nome="EMS", duracao_min=45, preparo_min=10, troca_min=10)
        usuario_gestor = Usuario.objects.create_user(
            "gestor", password="teste12345", papel=Usuario.Papel.GESTOR
        )
        self.gestor = usuario_gestor
        usuario = Usuario.objects.create_user("bia", password="teste12345", papel=Usuario.Papel.PROFESSOR)
        self.professor = Professor.objects.create(usuario=usuario)
        self.professor.tipos_habilitados.add(self.tipo)
        self.aluno = Aluno.objects.create(nome="Mariana")
        self.equipamento = Equipamento.objects.create(nome="Equip. 01")

    def test_painel_mostra_a_ocupacao_de_resumo_do_dia(self):
        hoje = timezone.localdate()
        inicio = timezone.make_aware(datetime.combine(hoje, datetime.min.time()) + timedelta(hours=10))
        fim = inicio + timedelta(minutes=self.tipo.duracao_min)
        servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=self.equipamento, inicio=inicio, fim=fim,
        )
        self.client.force_login(self.gestor)

        resposta_painel = self.client.get(reverse("painel:home"))

        pct_esperado = motor.resumo_do_dia(hoje)["ocupacao_pct"]
        self.assertContains(resposta_painel, "Ocupação hoje")
        self.assertContains(resposta_painel, f"{pct_esperado}%")


class NivelDeMovimentoTests(TestCase):
    """`motor.nivel_de_movimento` — usado tanto na faixa de dias da grade
    quanto no calendário de mês, por isso mora no motor (não na grade)."""

    def test_vazio_sem_sessoes(self):
        self.assertEqual(motor.nivel_de_movimento(0), "vazio")

    def test_baixo_dentro_do_limiar(self):
        self.assertEqual(motor.nivel_de_movimento(1), "baixo")
        self.assertEqual(motor.nivel_de_movimento(motor.NIVEL_BAIXO_MAX), "baixo")

    def test_medio_dentro_do_limiar(self):
        self.assertEqual(motor.nivel_de_movimento(motor.NIVEL_BAIXO_MAX + 1), "medio")
        self.assertEqual(motor.nivel_de_movimento(motor.NIVEL_MEDIO_MAX), "medio")

    def test_alto_acima_do_limiar(self):
        self.assertEqual(motor.nivel_de_movimento(motor.NIVEL_MEDIO_MAX + 1), "alto")


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class CalendarioMesTests(TestCase):
    """Visão de mês (`agenda:mes`): grade tradicional 7 colunas x semanas,
    contagem por dia e navegação entre meses."""

    def setUp(self):
        self.tipo = TipoSessao.objects.create(nome="EMS", duracao_min=45, preparo_min=10, troca_min=10)
        usuario_gestor = Usuario.objects.create_user(
            "gestor", password="teste12345", papel=Usuario.Papel.GESTOR
        )
        self.gestor = usuario_gestor
        usuario = Usuario.objects.create_user("bia", password="teste12345", papel=Usuario.Papel.PROFESSOR)
        self.professor = Professor.objects.create(usuario=usuario)
        self.professor.tipos_habilitados.add(self.tipo)
        self.aluno = Aluno.objects.create(nome="Mariana")
        self.equipamento = Equipamento.objects.create(nome="Equip. 01")
        self.client.force_login(self.gestor)

    def test_sem_parametro_usa_o_mes_atual(self):
        hoje = timezone.localdate()

        response = self.client.get(reverse("agenda:mes"))

        self.assertEqual(response.context["mes"], hoje.month)
        self.assertEqual(response.context["ano"], hoje.year)

    def test_mostra_a_contagem_certa_por_dia(self):
        hoje = timezone.localdate()
        dia_no_mes = hoje.replace(day=1) + timedelta(days=10)
        for hora in (9, 11, 13):
            inicio = timezone.make_aware(
                datetime.combine(dia_no_mes, datetime.min.time()) + timedelta(hours=hora)
            )
            fim = inicio + timedelta(minutes=self.tipo.duracao_min)
            servicos.agendar(
                professor=self.professor, aluno=self.aluno, tipo=self.tipo,
                equipamento=self.equipamento, inicio=inicio, fim=fim,
            )

        url = reverse("agenda:mes") + f"?ano={dia_no_mes.year}&mes={dia_no_mes.month}"
        response = self.client.get(url)

        self.assertContains(response, '<span class="badge-dia">3</span>')

    def test_inclui_dias_do_mes_anterior_e_seguinte_para_completar_a_semana(self):
        # Setembro de 2026 não começa num domingo nem termina num sábado —
        # garante dias de agosto/outubro na grade pra completar as semanas.
        url = reverse("agenda:mes") + "?ano=2026&mes=9"
        response = self.client.get(url)

        dias = response.context["dias"]
        self.assertEqual(len(dias) % 7, 0)
        self.assertTrue(any(not d["no_mes"] for d in dias))

    def test_navegacao_de_dezembro_para_janeiro_vira_o_ano(self):
        url = reverse("agenda:mes") + "?ano=2026&mes=12"
        response = self.client.get(url)

        self.assertEqual(response.context["mes_seguinte"], 1)
        self.assertEqual(response.context["ano_mes_seguinte"], 2027)

    def test_navegacao_de_janeiro_para_dezembro_vira_o_ano(self):
        url = reverse("agenda:mes") + "?ano=2026&mes=1"
        response = self.client.get(url)

        self.assertEqual(response.context["mes_anterior"], 12)
        self.assertEqual(response.context["ano_mes_anterior"], 2025)

    def test_clicar_num_dia_leva_para_a_grade_do_dia_certo(self):
        response = self.client.get(reverse("agenda:mes"))

        primeiro_dia = response.context["dias"][0]
        self.assertContains(
            response,
            reverse("agenda:grade") + f"?data={primeiro_dia['data'].isoformat()}",
        )

    def test_ano_fora_do_intervalo_valido_cai_pro_mes_atual_em_vez_de_quebrar(self):
        # `datetime.date` só aceita anos 1..9999 — sem tratar isso, `?ano=`
        # fora da faixa (ou um número absurdamente grande) derrubava a
        # página com erro 500 em vez de simplesmente ignorar o parâmetro.
        hoje = timezone.localdate()
        for querystring in ("?ano=0&mes=1", "?ano=-5&mes=3", "?ano=99999999999999&mes=1"):
            with self.subTest(querystring=querystring):
                response = self.client.get(reverse("agenda:mes") + querystring)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["ano"], hoje.year)
                self.assertEqual(response.context["mes"], hoje.month)

    def test_ano_mes_no_limite_do_calendario_cai_pro_mes_atual_em_vez_de_quebrar(self):
        # ano=1/mes=1 e ano=9999/mes=12 passam pela validação de "é uma data
        # válida", mas os dias de padding no início/fim da grade (pra
        # completar a semana) pertencem ao ano anterior/seguinte — ano 0 ou
        # 10000, que não existem — e derrubavam a página mesmo assim.
        hoje = timezone.localdate()
        for querystring in ("?ano=1&mes=1", "?ano=9999&mes=12"):
            with self.subTest(querystring=querystring):
                response = self.client.get(reverse("agenda:mes") + querystring)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["ano"], hoje.year)
                self.assertEqual(response.context["mes"], hoje.month)


class MotorContagemPorMesTests(TestCase):
    """Teste unitário direto de `motor.contagem_por_mes_do_ano`, sem HTTP —
    mesmo padrão de `ContagemPorDiaTests`."""

    def setUp(self):
        self.tipo = TipoSessao.objects.create(nome="EMS", duracao_min=45)
        usuario = Usuario.objects.create_user("bia", papel=Usuario.Papel.PROFESSOR)
        self.professor = Professor.objects.create(usuario=usuario)
        self.professor.tipos_habilitados.add(self.tipo)
        self.aluno = Aluno.objects.create(nome="Mariana")
        self.equipamento = Equipamento.objects.create(nome="Equip. 01")

    def test_soma_por_mes_e_ignora_cancelada(self):
        ano = timezone.localdate().year + 1  # ano fixo e sem sessões de outros testes

        for mes, dia, qtd in [(3, 10, 2), (3, 20, 1), (8, 5, 1)]:
            for hora in range(9, 9 + qtd):
                inicio = timezone.make_aware(
                    datetime(ano, mes, dia) + timedelta(hours=hora)
                )
                servicos.agendar(
                    professor=self.professor, aluno=self.aluno, tipo=self.tipo,
                    equipamento=self.equipamento, inicio=inicio, fim=inicio + timedelta(minutes=45),
                )

        inicio_cancelada = timezone.make_aware(datetime(ano, 12, 1, 10))
        sessao_cancelada = servicos.agendar(
            professor=self.professor, aluno=self.aluno, tipo=self.tipo,
            equipamento=self.equipamento, inicio=inicio_cancelada, fim=inicio_cancelada + timedelta(minutes=45),
        )
        servicos.cancelar(sessao=sessao_cancelada)

        por_mes = motor.contagem_por_mes_do_ano(ano)

        self.assertEqual(por_mes[3], 3)
        self.assertEqual(por_mes[8], 1)
        self.assertEqual(por_mes[12], 0)
        self.assertEqual(por_mes[1], 0)
        self.assertEqual(len(por_mes), 12)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class CalendarioAnoTests(TestCase):
    """Visão de ano (`agenda:ano`): 12 meses em cards, contagem por mês e
    navegação entre anos."""

    def setUp(self):
        self.tipo = TipoSessao.objects.create(nome="EMS", duracao_min=45, preparo_min=10, troca_min=10)
        usuario_gestor = Usuario.objects.create_user(
            "gestor", password="teste12345", papel=Usuario.Papel.GESTOR
        )
        self.gestor = usuario_gestor
        usuario = Usuario.objects.create_user("bia", password="teste12345", papel=Usuario.Papel.PROFESSOR)
        self.professor = Professor.objects.create(usuario=usuario)
        self.professor.tipos_habilitados.add(self.tipo)
        self.aluno = Aluno.objects.create(nome="Mariana")
        self.equipamento = Equipamento.objects.create(nome="Equip. 01")
        self.client.force_login(self.gestor)

    def test_sem_parametro_usa_o_ano_atual(self):
        hoje = timezone.localdate()

        response = self.client.get(reverse("agenda:ano"))

        self.assertEqual(response.context["ano"], hoje.year)

    def test_soma_totais_por_mes_corretamente(self):
        ano = timezone.localdate().year

        inicio_marco = timezone.make_aware(datetime(ano, 3, 10, 9))
        inicio_agosto_1 = timezone.make_aware(datetime(ano, 8, 5, 9))
        inicio_agosto_2 = timezone.make_aware(datetime(ano, 8, 5, 11))
        for inicio in (inicio_marco, inicio_agosto_1, inicio_agosto_2):
            servicos.agendar(
                professor=self.professor, aluno=self.aluno, tipo=self.tipo,
                equipamento=self.equipamento, inicio=inicio, fim=inicio + timedelta(minutes=45),
            )

        response = self.client.get(reverse("agenda:ano") + f"?ano={ano}")

        self.assertEqual(response.context["total_ano"], 3)
        meses = {m["numero"]: m["qtd"] for m in response.context["meses"]}
        self.assertEqual(meses[3], 1)
        self.assertEqual(meses[8], 2)
        self.assertEqual(meses[1], 0)

    def test_navegacao_entre_anos(self):
        response = self.client.get(reverse("agenda:ano") + "?ano=2026")

        self.assertEqual(response.context["ano_anterior"], 2025)
        self.assertEqual(response.context["ano_seguinte"], 2027)

    def test_clicar_num_mes_leva_para_o_calendario_daquele_mes(self):
        response = self.client.get(reverse("agenda:ano") + "?ano=2026")

        mes = response.context["meses"][2]  # março
        self.assertContains(
            response,
            reverse("agenda:mes") + f"?ano=2026&mes={mes['numero']}",
        )

    def test_ano_fora_do_intervalo_valido_cai_pro_ano_atual_em_vez_de_quebrar(self):
        # `datetime.date` só aceita anos 1..9999 — sem tratar isso, `?ano=`
        # fora da faixa (ou um número absurdamente grande) derrubava a
        # página com erro 500 em vez de simplesmente ignorar o parâmetro.
        hoje = timezone.localdate()
        for querystring in ("?ano=10000", "?ano=-1", "?ano=99999999999999"):
            with self.subTest(querystring=querystring):
                response = self.client.get(reverse("agenda:ano") + querystring)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["ano"], hoje.year)
