import logging
import os
from logging.handlers import RotatingFileHandler

log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)

def setup_logging():
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    general_log_file = os.path.join(log_dir, 'bot.log')
    file_handler = RotatingFileHandler(general_log_file, maxBytes=5*1024*1024, backupCount=5)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    music_log_file = os.path.join(log_dir, 'music.log')
    music_file_handler = RotatingFileHandler(music_log_file, maxBytes=5*1024*1024, backupCount=5)
    music_file_handler.setFormatter(formatter)
    music_file_handler.setLevel(logging.DEBUG)
    
    stats_log_file = os.path.join(log_dir, 'statistics.log')
    stats_file_handler = RotatingFileHandler(stats_log_file, maxBytes=5*1024*1024, backupCount=5)
    stats_file_handler.setFormatter(formatter)
    stats_file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    music_logger = logging.getLogger('music')
    music_logger.setLevel(logging.DEBUG)
    music_logger.addHandler(music_file_handler)
    
    stats_logger = logging.getLogger('bot.statistics')
    stats_logger.setLevel(logging.DEBUG)
    stats_logger.addHandler(stats_file_handler)
    
    return root_logger, music_logger