"""
Cria usuários e dados de demonstração:
gestora (Carla), administrador (Admin), professores (Bia, Leo, Felipe) e aluna (Mariana),
mais equipamentos, tipo de sessão, planos e algumas sessões de exemplo.
Senha de todos: demo1234
"""
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.agenda import servicos
from apps.cadastros.models import Aluno, Equipamento, Professor, TipoSessao
from apps.contas.models import Usuario
from apps.planos.models import Contratacao, Plano

SENHA_DEMO = "demo1234"


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
