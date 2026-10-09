# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import logging
import sys
import contextvars
import threading
import queue
import requests
import json
import time
from datetime import datetime, timezone
from pythonjsonlogger import jsonlogger
from .config import settings

request_id_var = contextvars.ContextVar("request_id", default=None)

# Secrets to redact
SECRETS = ["token", "secret", "password", "key", "authorization", "cookie"]

class RedactingJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        
        if not log_record.get('timestamp'):
            now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            log_record['timestamp'] = now
            
        if log_record.get('level'):
            log_record['level'] = log_record['level'].upper()
        else:
            log_record['level'] = record.levelname
            
        req_id = request_id_var.get()
        if req_id:
            log_record["request_id"] = req_id
            
        log_record["environment"] = "local" if not settings.axiom_token else "production"
        log_record["service_name"] = "social-media-llm"
        
        # Redact secrets
        for key, value in list(log_record.items()):
            if any(s in key.lower() for s in SECRETS) and isinstance(value, str):
                log_record[key] = "***REDACTED***"

class AxiomHandler(logging.Handler):
    """Ships logs to Axiom via HTTP in the background."""
    def __init__(self):
        super().__init__()
        self.queue = queue.Queue(maxsize=10000)
        self._delivery_lock = threading.Lock()
        self._unconfirmed_events = 0
        self._failed_batches = 0
        self._last_delivery_notice = None
        self.worker = threading.Thread(target=self._ship_logs, daemon=True)
        self.worker.start()
        
    def _ship_logs(self):
        batch = []
        while True:
            try:
                record = self.queue.get(timeout=3.0)
                batch.append(record)
            except queue.Empty:
                pass
                
            if batch and (len(batch) >= 50 or getattr(self.queue, 'empty', lambda: True)()):
                self._send_to_axiom(batch)
                batch = []

    def _send_to_axiom(self, batch):
        if not settings.axiom_token or not settings.axiom_dataset:
            self._delivery_notice(False, len(batch), "not_configured")
            return False
            
        url = f"{settings.axiom_url.rstrip('/')}/v1/datasets/{settings.axiom_dataset}/ingest"
        headers = {
            "Authorization": f"Bearer {settings.axiom_token}",
            "Content-Type": "application/json"
        }
        if settings.axiom_org_id:
            headers["X-Axiom-Org-Id"] = settings.axiom_org_id
            
        try:
            response = requests.post(url, headers=headers, json=batch, timeout=5.0)
            if not 200 <= response.status_code < 300:
                self._delivery_notice(False, len(batch), "http_rejected", response.status_code)
                return False
            result = response.json()
            if not isinstance(result, dict) or result.get("failed") != 0 or result.get("ingested") != len(batch):
                self._delivery_notice(False, len(batch), "unconfirmed_ingestion")
                return False
        except Exception:
            self._delivery_notice(False, len(batch), "request_failed")
            return False
        self._delivery_notice(True, 0)
        return True

    def _delivery_notice(self, success, count, reason=None, status=None):
        """Report to Railway's console directly, never back through this handler.

        Do not include log payloads, response bodies, URLs or exception strings.
        Unconfirmed counts can include a partially accepted batch; no blind retry.
        """
        try:
            with self._delivery_lock:
                if success and not self._failed_batches:
                    return
                if not success:
                    self._failed_batches += 1
                    self._unconfirmed_events += count
                now = time.monotonic()
                if not success and self._last_delivery_notice is not None and now - self._last_delivery_notice < 60:
                    return
                notice = {"event": "log_delivery_recovered" if success else "log_delivery_failed",
                          "level": "INFO" if success else "ERROR", "reason": reason,
                          "http_status": status, "failed_batches": self._failed_batches,
                          "unconfirmed_events": self._unconfirmed_events}
                sys.stderr.write(json.dumps(notice) + "\n")
                self._last_delivery_notice = now
                if success:
                    self._failed_batches = self._unconfirmed_events = 0
                    self._last_delivery_notice = None
        except Exception:
            pass  # Observability failures cannot break application requests.
            
    def emit(self, record):
        if not settings.axiom_token:
            return
            
        try:
            log_entry = self.format(record)
            self.queue.put_nowait(json.loads(log_entry))
        except Exception:
            self._delivery_notice(False, 1, "queue_or_format_failed")

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Clean up any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    formatter = RedactingJsonFormatter('%(timestamp)s %(level)s %(name)s %(message)s')
    
    # 1. Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 2. Axiom handler
    if settings.axiom_token:
        axiom_handler = AxiomHandler()
        axiom_handler.setFormatter(formatter)
        logger.addHandler(axiom_handler)
        
    # Tone down noisy uvicorn access logs
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # OAuth exchanges put credentials in query parameters under Meta's contract.
    # httpx INFO logs full request URLs; never ship those to console or Axiom.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

def log_event(event: str, level: str = "info", **fields):
    """Helper method to log structured JSON events cleanly."""
    logger = logging.getLogger("social-media-llm")
    fields["event"] = event
    
    msg_fields = {k: v for k,v in fields.items() if v is not None}
    
    if level.lower() == "debug":
        logger.debug(event, extra=msg_fields)
    elif level.lower() == "warning":
        logger.warning(event, extra=msg_fields)
    elif level.lower() == "error":
        logger.error(event, extra=msg_fields)
    else:
        logger.info(event, extra=msg_fields)
