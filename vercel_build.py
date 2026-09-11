"""
Script de build executado pela Vercel (tool.vercel.scripts.build no
pyproject.toml): aplica migrações e popula dados de demonstração.
Roda depois do `pip install` e antes do deploy; não precisa chamar
collectstatic aqui, a Vercel já faz isso automaticamente.
"""
import subprocess
import sys


def main():
    subprocess.run([sys.executable, "manage.py", "migrate", "--no-input"], check=True)
    subprocess.run([sys.executable, "manage.py", "popular_demo"], check=True)


if __name__ == "__main__":
    main()
