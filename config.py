"""Configurações do Portal Operações RNO."""
import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me-in-production")
    APP_NAME = "Portal Operações RNO"
    APP_VERSION = "v1.0"
    USER_NAME = "Mauro Gonçalves"
    USER_INITIALS = "MG"
