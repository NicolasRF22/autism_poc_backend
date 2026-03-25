import os
import re
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Deque, Dict, Optional, Tuple


Event = Tuple[datetime, int]

_events_by_model: Dict[str, Deque[Event]] = defaultdict(deque)
_lock = Lock()


def _safe_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == '':
        return None
    try:
        parsed = int(value)
        return parsed if parsed >= 0 else None
    except ValueError:
        return None


def _sanitize_model_for_env(model: str) -> str:
    return re.sub(r'[^A-Z0-9]', '_', model.upper())


def _resolve_limit(model: str, metric: str) -> Optional[int]:
    metric = metric.upper()
    model_key = _sanitize_model_for_env(model)
    specific = os.getenv(f'GOOGLE_RATE_LIMIT_{model_key}_{metric}')
    if specific is not None:
        return _safe_int(specific)
    default_value = os.getenv(f'GOOGLE_RATE_LIMIT_DEFAULT_{metric}')
    return _safe_int(default_value)


def _estimate_input_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def extract_input_tokens(result, fallback_text: str = '') -> int:
    usage = getattr(result, 'usage_metadata', None)
    if usage:
        for field in ('prompt_token_count', 'input_token_count', 'total_token_count'):
            value = getattr(usage, field, None)
            if isinstance(value, int) and value >= 0:
                return value
    return _estimate_input_tokens(fallback_text)


def record_model_usage(model: str, input_tokens: int) -> None:
    if not model:
        return
    now = datetime.now(timezone.utc)
    tokens = max(0, int(input_tokens or 0))

    with _lock:
        queue = _events_by_model[model]
        queue.append((now, tokens))
        _prune(queue, now)


def _prune(queue: Deque[Event], now: datetime) -> None:
    day_ago = now - timedelta(days=1)
    while queue and queue[0][0] < day_ago:
        queue.popleft()


def _sum_window(queue: Deque[Event], since: datetime) -> Tuple[int, int]:
    requests = 0
    tokens = 0
    for ts, input_tokens in queue:
        if ts >= since:
            requests += 1
            tokens += input_tokens
    return requests, tokens


def _percent(current: int, limit: Optional[int]) -> Optional[float]:
    if limit is None or limit <= 0:
        return None
    return round((current / limit) * 100, 2)


def _status_from_utilization(rpm_pct: Optional[float], tpm_pct: Optional[float], rpd_pct: Optional[float]) -> str:
    values = [v for v in (rpm_pct, tpm_pct, rpd_pct) if v is not None]
    if not values:
        return 'sem_limite_configurado'
    highest = max(values)
    if highest >= 90:
        return 'critico'
    if highest >= 70:
        return 'atencao'
    return 'ok'


def get_usage_snapshot(additional_models: Optional[list] = None) -> Dict:
    now = datetime.now(timezone.utc)
    minute_ago = now - timedelta(minutes=1)
    day_ago = now - timedelta(days=1)

    with _lock:
        tracked_models = set(_events_by_model.keys())
        if additional_models:
            tracked_models.update([m for m in additional_models if m])

        models_payload = []
        for model in sorted(tracked_models):
            queue = _events_by_model.get(model, deque())
            _prune(queue, now)

            rpm_current, tpm_current = _sum_window(queue, minute_ago)
            rpd_current, _ = _sum_window(queue, day_ago)

            limits = {
                'rpm': _resolve_limit(model, 'RPM'),
                'tpm': _resolve_limit(model, 'TPM'),
                'rpd': _resolve_limit(model, 'RPD'),
            }

            utilization = {
                'rpm_percent': _percent(rpm_current, limits['rpm']),
                'tpm_percent': _percent(tpm_current, limits['tpm']),
                'rpd_percent': _percent(rpd_current, limits['rpd']),
            }

            models_payload.append(
                {
                    'model': model,
                    'current': {
                        'rpm': rpm_current,
                        'tpm': tpm_current,
                        'rpd': rpd_current,
                    },
                    'limits': limits,
                    'utilization': utilization,
                    'status': _status_from_utilization(
                        utilization['rpm_percent'],
                        utilization['tpm_percent'],
                        utilization['rpd_percent'],
                    ),
                }
            )

    return {
        'generated_at': now.isoformat(),
        'models': models_payload,
        'notes': {
            'tpm_definition': 'TPM calculado com tokens de entrada no último minuto',
            'limits_source': 'Variáveis de ambiente GOOGLE_RATE_LIMIT_*',
        },
    }
