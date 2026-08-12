"""Configurações do Portal Operações RNO."""
import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me-in-production")
    APP_NAME = "Portal Operações RNO"
    APP_VERSION = "v1.0"
    USER_NAME = "Mauro Gonçalves"
    USER_INITIALS = "MG"

    # Credenciais do MySQL (sobrescrever via variáveis de ambiente em produção)
    DB_HOST = os.environ.get("MYSQL_HOST", "localhost")
    DB_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
    DB_USER = os.environ.get("MYSQL_USER", "root")
    DB_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
    DB_NAME = os.environ.get("MYSQL_DATABASE", "safra")

    @classmethod
    def db_url(cls):
        """URL SQLAlchemy para pandas/SQLAlchemy (sem charset)."""
        return f"mysql+pymysql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"

    @classmethod
    def db_config_pymysql(cls):
        """Dict de conexão para pymysql.connect(**...)."""
        return {
            "host": cls.DB_HOST,
            "user": cls.DB_USER,
            "password": cls.DB_PASSWORD,
            "database": cls.DB_NAME,
            "port": cls.DB_PORT,
            "charset": "utf8mb4",
        }
