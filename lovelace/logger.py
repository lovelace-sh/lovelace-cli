import logging
import sys
from pathlib import Path
from typing import Optional

def setup_logging(verbose: bool = False, log_file: Optional[Path] = None):
    log_level = logging.DEBUG if verbose else logging.INFO
    
    format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    handlers = []
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(
        '%(levelname)s: %(message)s' if not verbose else format_string,
        datefmt=date_format
    )
    console_handler.setFormatter(console_formatter)
    handlers.append(console_handler)
    
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(format_string, datefmt=date_format)
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)
    
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=handlers
    )
    
    logging.getLogger('boto3').setLevel(logging.WARNING)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('websocket').setLevel(logging.WARNING)