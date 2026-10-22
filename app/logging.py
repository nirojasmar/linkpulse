import datetime
import json
import logging
import sys
from typing import Any


class JSONFormatter(logging.Formatter):
    def __init__(self, pod_name: str = "local"):
        super().__init__()
        self.pod_name = pod_name

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "pod": getattr(record, "pod", self.pod_name),
        }

        # Add optional standard and extra fields if present
        for field in (
            "request_id",
            "path",
            "status",
            "duration_ms",
            "target",
            "error",
            "config",
            "count",
        ):
            val = getattr(record, field, None)
            if val is not None:
                log_data[field] = val

        if record.exc_info and not log_data.get("error"):
            log_data["error"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_logging(log_level: str = "INFO", pod_name: str = "local") -> logging.Logger:
    level = getattr(logging, log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter(pod_name=pod_name))
    root.addHandler(handler)

    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False

    logger = logging.getLogger("linkpulse")
    return logger


def get_logger(name: str = "linkpulse") -> logging.Logger:
    return logging.getLogger(name)
