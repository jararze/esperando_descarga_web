import os
from urllib.parse import urlparse


def get_database_config():
    """Configuración de base de datos para desarrollo y producción"""

    if os.getenv('FLASK_ENV') == 'production':
        # En producción usar PostgreSQL de Render
        database_url = os.environ.get('DATABASE_URL')
        if database_url:
            url = urlparse(database_url)
            return {
                'type': 'postgresql',
                'host': url.hostname,
                'user': url.username,
                'password': url.password,
                'database': url.path[1:],
                'port': url.port or 5432
            }

    # En desarrollo usar MySQL local
    return {
        'type': 'mysql',
        'host': os.getenv('DB_HOST', '159.203.123.109'),
        'user': os.getenv('DB_USER', 'hnsrqkzfpr'),
        'password': os.getenv('DB_PASSWORD', 'FdF6rJB6Ma'),
        'database': os.getenv('DB_NAME', 'hnsrqkzfpr'),
        'port': int(os.getenv('DB_PORT', 3306))
    }