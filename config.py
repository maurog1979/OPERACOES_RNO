"""Configurações do Portal Operações RNO."""
import os
import secrets
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.engine import URL

load_dotenv(Path(__file__).resolve().parent / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
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

    CACHE_TTL_SECONDS = max(0, int(os.environ.get("CACHE_TTL_SECONDS", "300")))
    PRELOAD_DATA = os.environ.get("PRELOAD_DATA", "0").lower() in {"1", "true", "yes"}
    ENABLE_DIAGNOSTICS = os.environ.get("ENABLE_DIAGNOSTICS", "0").lower() in {"1", "true", "yes"}
    DB_CONNECT_TIMEOUT = int(os.environ.get("MYSQL_CONNECT_TIMEOUT", "5"))
    DB_READ_TIMEOUT = int(os.environ.get("MYSQL_READ_TIMEOUT", "60"))

    @classmethod
    def db_url(cls):
        """Preserva senhas com @, /, : e outros caracteres reservados."""
        return URL.create("mysql+pymysql", username=cls.DB_USER,
                          password=cls.DB_PASSWORD, host=cls.DB_HOST,
                          port=cls.DB_PORT, database=cls.DB_NAME,
                          query={"charset": "utf8mb4"})

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
            "connect_timeout": cls.DB_CONNECT_TIMEOUT,
            "read_timeout": cls.DB_READ_TIMEOUT,
            "write_timeout": cls.DB_READ_TIMEOUT,
        }

