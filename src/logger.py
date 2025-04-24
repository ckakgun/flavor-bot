import logging
import os
from datetime import datetime

LOG_FILE = f'{datetime.now().strftime('%m_%d_%Y_%H_%M_%S')}.log'
logs_dir = os.path.join(os.getcwd(), 'logs')
os.makedirs(logs_dir, exist_ok=True)

def setup_logger():
    """Configure and return a logger instance."""
    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'INFO'),
        format=os.getenv('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    )
    return logging.getLogger(__name__)



if __name__ == '__main__':
    logger=setup_logger()
    logger.info('Logging has started')
