import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime

def setup_logger(name: str = None) -> logging.Logger:
    """
    Configura um logger que escreve em ficheiro (com rotação) e na consola.
    Se 'name' não for passado, usa o nome do módulo raiz.
    """
    
    # 1. Criar pasta de logs se não existir
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 2. Definir nome do arquivo
    data_hoje = datetime.now().strftime('%Y-%m-%d')
    log_filename = f"{log_dir}/app_{data_hoje}.log"

    # 3. Obter o logger
    logger = logging.getLogger(name if name else "HanaToIbid")
    logger.setLevel(logging.INFO)

    # 4. Evitar duplicar logs
    if logger.hasHandlers():
        return logger

    # 5. Formato da mensagem
    # Ex: 2026-02-13 14:00:01 | INFO | processador_dados | Mensagem...
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(module)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 6. Handler Arquivo
    # Roda o ficheiro se passar de 5MB, guarda os últimos 5
    file_handler = RotatingFileHandler(log_filename, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    # 7. Handler Consola (Mostra no terminal)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger