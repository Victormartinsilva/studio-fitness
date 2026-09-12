"""
Cria usuários e dados de demonstração:
gestora (Carla), administrador (Admin), professores (Bia, Leo, Felipe) e aluna (Mariana),
mais equipamentos, tipo de sessão, planos e sessões de exemplo espalhadas pelos
próximos 14 dias (pra faixa de dias da grade ter contagem/nível pra mostrar) e
um bloqueio de equipamento (pra ter ocupação "real" descontada na grade).
Senha de todos: demo1234
"""
import random
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.agenda import servicos
from apps.agenda.models import BloqueioEquipamento
from apps.cadastros.models import Aluno, Equipamento, Professor, TipoSessao
from apps.contas.models import Usuario
from apps.planos.models import Contratacao, Plano

SENHA_DEMO = "demo1234"

# Dias de agenda de demonstração a espalhar a partir de hoje (inclusive) e
# horas candidatas por dia — fixo (sem `random.seed` global) pra o comando
# gerar sempre a mesma agenda a cada execução, já que `agendar` é idempotente
# na prática (colisão de horário só é ignorada via try/except, ver abaixo).
DIAS_DEMO = 14
HORAS_CANDIDATAS = [8, 9, 10, 13, 14, 15, 16, 17]


class Command(BaseCommand):
    help = "Popula o banco com usuários e dados de demonstração."

    def handle(self, *args, **options):
        gestora = self._criar_usuario(
            "gestor", "Carla", "Gestora", Usuario.Papel.GESTOR, is_staff=True
        )
        self._criar_usuario(
            "adm", "Admin", "Studio Fitness", Usuario.Papel.GESTOR, is_staff=True, is_superuser=True
        )

        professores = {}
        for username, nome, sobrenome in [
            ("bia", "Bia", "Rocha"),
            ("leo", "Leo", "Martins"),
            ("felipe", "Felipe", "Costa"),
        ]:
            usuario = self._criar_usuario(username, nome, sobrenome, Usuario.Papel.PROFESSOR)
            professor, _ = Professor.objects.get_or_create(usuario=usuario)
            professores[username] = professor

        mariana_usuario = self._criar_usuario("mariana", "Mariana", "Lopes", Usuario.Papel.ALUNO)
        aluna_mariana, _ = Aluno.objects.get_or_create(
            usuario=mariana_usuario, defaults={"nome": "Mariana Lopes", "telefone": "(13) 99999-0000"}
        )
        outros_alunos = []
        for nome in ["Pedro Alves", "Ana Souza", "Lucas Lima"]:
            aluno, _ = Aluno.objects.get_or_create(nome=nome, defaults={"telefone": "(13) 99999-0000"})
            outros_alunos.append(aluno)

        equipamentos = []
        for i in range(1, 6):
            status = Equipamento.Status.MANUTENCAO if i == 3 else Equipamento.Status.ATIVO
            equipamento, _ = Equipamento.objects.get_or_create(
                nome=f"Equip. {i:02d}", defaults={"status": status}
            )
            equipamentos.append(equipamento)

        tipo_sessao, _ = TipoSessao.objects.get_or_create(
            nome="Eletroestimulação (EMS)",
            defaults={
                "duracao_min": 45,
                "preparo_min": 20,
                "troca_min": 15,
                "requer_equipamento": True,
                "professor_no_preparo": True,
            },
        )
        for professor in professores.values():
            professor.tipos_habilitados.add(tipo_sessao)

        plano_mensal, _ = Plano.objects.get_or_create(
            nome="Mensal 2x/semana",
            defaults={"modalidade": Plano.Modalidade.RECORRENTE, "sessoes_por_semana": 2},
        )
        plano_10, _ = Plano.objects.get_or_create(
            nome="Pacote 10 sessões",
            defaults={
                "modalidade": Plano.Modalidade.PACOTE,
                "quantidade_sessoes": 10,
                "validade_dias": 60,
            },
        )
        plano_5, _ = Plano.objects.get_or_create(
            nome="Pacote 5 sessões",
            defaults={
                "modalidade": Plano.Modalidade.PACOTE,
                "quantidade_sessoes": 5,
                "validade_dias": 30,
            },
        )

        contratacao_mariana, _ = Contratacao.objects.get_or_create(
            aluno=aluna_mariana,
            plano=plano_mensal,
            defaults={"data_inicio": timezone.localdate() - timedelta(days=40)},
        )

        hoje = timezone.localdate()
        inicio_base = timezone.make_aware(datetime.combine(hoje, datetime.min.time())) + timedelta(hours=11)
        try:
            servicos.agendar(
                professor=professores["bia"],
                aluno=aluna_mariana,
                tipo=tipo_sessao,
                inicio=inicio_base + timedelta(minutes=20),
                fim=inicio_base + timedelta(minutes=65),
                equipamento=equipamentos[0],
                contratacao=contratacao_mariana,
                usuario=gestora,
            )
        except Exception:
            pass

        # Sessões variadas nos próximos 14 dias (professor/equipamento/horário
        # diferentes), pra grade (Etapa 2) ter contagem/nível de ocupação real
        # pra mostrar. `servicos.agendar` já valida tudo (professor, equipamento,
        # aluno, expediente) — se o horário sorteado colidir por acaso com outra
        # sessão, só ignora e segue, como já fazia a sessão-âncora acima.
        equipamentos_ativos = [e for e in equipamentos if e.status == Equipamento.Status.ATIVO]
        professores_lista = list(professores.values())
        alunos_para_sessoes = [aluna_mariana] + outros_alunos
        rng = random.Random(42)  # fixo: mesma agenda de demo a cada execução

        for dia_offset in range(DIAS_DEMO):
            dia = hoje + timedelta(days=dia_offset)
            quantidade_no_dia = rng.randint(2, 5)
            horas_do_dia = rng.sample(HORAS_CANDIDATAS, k=min(quantidade_no_dia, len(HORAS_CANDIDATAS)))

            for hora in horas_do_dia:
                inicio = timezone.make_aware(datetime.combine(dia, time(hora, 0)))
                fim = inicio + timedelta(minutes=tipo_sessao.duracao_min)
                professor = rng.choice(professores_lista)
                equipamento = rng.choice(equipamentos_ativos)
                aluno = rng.choice(alunos_para_sessoes)
                try:
                    servicos.agendar(
                        professor=professor,
                        aluno=aluno,
                        tipo=tipo_sessao,
                        inicio=inicio,
                        fim=fim,
                        equipamento=equipamento,
                        usuario=gestora,
                    )
                except Exception:
                    pass

        # Bloqueio de equipamento (ex.: manutenção de manhã) pra Etapa 1/2
        # terem uma ocupação real descontando vaga na grade/painel.
        manha_amanha = timezone.make_aware(datetime.combine(hoje + timedelta(days=1), time(8, 0)))
        BloqueioEquipamento.objects.get_or_create(
            equipamento=equipamentos_ativos[0],
            inicio=manha_amanha,
            fim=manha_amanha + timedelta(hours=2),
            defaults={
                "motivo": BloqueioEquipamento.Motivo.MANUTENCAO,
                "descricao": "Manutenção preventiva agendada (demo).",
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Dados de demonstração criados. Login: adm, gestor, bia, leo, felipe, mariana "
                f"(senha: {SENHA_DEMO})"
            )
        )

    def _criar_usuario(self, username, primeiro_nome, sobrenome, papel, is_staff=False, is_superuser=False):
        usuario, _ = Usuario.objects.get_or_create(
            username=username,
            defaults={
                "first_name": primeiro_nome,
                "last_name": sobrenome,
                "papel": papel,
                "is_staff": is_staff,
                "is_superuser": is_superuser,
            },
        )
        usuario.set_password(SENHA_DEMO)
        usuario.papel = papel
        usuario.is_staff = is_staff or usuario.is_staff
        usuario.is_superuser = is_superuser or usuario.is_superuser
        usuario.save()
        return usuario
