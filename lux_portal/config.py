#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuracion del Portal Lux
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuracion base."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'lux-portal-clave-secreta-2025'

    # Credenciales de acceso
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'Daniela')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'freightwise2025')

    # Base de datos - Railway provee DATABASE_URL automaticamente
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///lux_portal.db')

    # Railway usa postgres:// pero SQLAlchemy necesita postgresql://
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)

    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    """Configuracion de desarrollo."""
    DEBUG = True


class ProductionConfig(Config):
    """Configuracion de produccion."""
    DEBUG = False


# Seleccionar configuracion segun entorno
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config(config_name='default'):
    """Obtiene la configuracion segun la variable de entorno."""
    if config_name == 'default':
        env = os.environ.get('FLASK_ENV', 'development')
        return config.get(env, config['default'])
    return config.get(config_name, config['default'])
