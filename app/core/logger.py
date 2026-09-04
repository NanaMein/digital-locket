import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo


class UTCManilaFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        utc_time = ZoneInfo("Asia/Manila")        
        dt = datetime.fromtimestamp(record.created, tz=utc_time)
        return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{dt.microsecond // 1000:03d} +08:00"

def setup_master_logger() -> logging.Logger:
    logger = logging.getLogger("Nana_Logger")    
    logger.setLevel(logging.DEBUG) 

    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)

        log_format = "%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)d | %(message)s"

        formatter = UTCManilaFormatter(fmt=log_format)
        console_handler.setFormatter(formatter)

        logger.addHandler(console_handler)

    return logger

app_logger = setup_master_logger()