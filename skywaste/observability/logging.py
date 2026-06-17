import logging
import json
import os
import sys
from datetime import datetime, timezone

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Check if handler already set
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        # Use simple format for CLI readability, or json formatting
        if os.getenv("LOG_FORMAT", "text").lower() == "json":
            handler.setFormatter(JSONFormatter())
        else:
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
            handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger
