import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from prometheus_client import CollectorRegistry, Counter, Histogram, Gauge

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({"time":datetime.now(timezone.utc).isoformat(),
            "level":record.levelname, "event":record.getMessage(),
            **getattr(record, "fields", {})})

def setup_logging(path, max_bytes, backups):
    path.parent.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("production_ai")
    log.setLevel(logging.INFO)
    for old in log.handlers[:]:
        old.close()
        log.removeHandler(old)
    for handler in (logging.StreamHandler(), RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups)):
        handler.setFormatter(JsonFormatter())
        log.addHandler(handler)
    log.propagate = False
    return log

class Metrics:
    def __init__(self):
        self.registry = CollectorRegistry()
        self.requests = Counter("ai_http_requests_total", "HTTP requests", ["route","status"], registry=self.registry)
        self.latency = Histogram("ai_http_duration_seconds", "HTTP latency", ["route"], registry=self.registry)
        self.blocks = Counter("ai_guardrail_blocks_total", "Guardrail blocks", ["stage"], registry=self.registry)
        self.failures = Counter("ai_model_failures_total", "Model failures", registry=self.registry)
        self.active = Gauge("ai_active_generations", "Active generations", registry=self.registry)
