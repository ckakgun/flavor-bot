import logging
import os
from datetime import datetime

def setup_logger():
    """Configure and return a logger instance."""
    # Create timestamp for log file name
    timestamp = datetime.now().strftime('%m_%d_%Y_%H_%M_%S')
    LOG_FILE = f'{timestamp}.log'
    
    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(os.getcwd(), 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    # Full path to log file
    log_file_path = os.path.join(logs_dir, LOG_FILE)
    
    # Configure logging with both console and file handlers
    logger = logging.getLogger(__name__)
    logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))
    
    # Format for logs
    formatter = logging.Formatter(
        os.getenv('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # File handler
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(formatter)
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    logger.info(f'Logging to {log_file_path}')
    return logger


if __name__ == '__main__':
    logger = setup_logger()
    logger.info('Logging has started')
