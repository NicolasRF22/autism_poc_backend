import os
import re
import json
from collections import defaultdict, deque
from datetime import datetime, timedelta
from threading import Lock
from typing import Deque, Dict, Optional, Tuple

from time_utils import now_brasilia


Event = Tuple[datetime, int, int, int, str]

_events_by_model: Dict[str, Deque[Event]] = defaultdict(deque)
_lock = Lock()
_usage_log_dir = os.getenv('USAGE_LOG_DIR', os.path.join(os.path.dirname(__file__), 'usage_logs'))
_usage_log_path = os.path.join(_usage_log_dir, 'events.jsonl')
os.makedirs(_usage_log_dir, exist_ok=True)

if not os.path.exists(_usage_log_path):
    with open(_usage_log_path, 'w', encoding='utf-8') as f:
        f.write('')


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


def _usage_get(usage, *fields: str) -> Optional[int]:
    for field in fields:
        value = getattr(usage, field, None)
        if isinstance(value, int) and value >= 0:
            return value
    if isinstance(usage, dict):
        for field in fields:
            value = usage.get(field)
            if isinstance(value, int) and value >= 0:
                return value
    return None


def extract_usage_metrics(result, fallback_text: str = '') -> Dict[str, int]:
    usage = getattr(result, 'usage_metadata', None)

    input_tokens = None
    output_tokens = None
    total_tokens = None

    if usage:
        input_tokens = _usage_get(usage, 'prompt_token_count', 'input_token_count')
        output_tokens = _usage_get(usage, 'candidates_token_count', 'output_token_count')
        total_tokens = _usage_get(usage, 'total_token_count')

    if input_tokens is None:
        input_tokens = _estimate_input_tokens(fallback_text)

    if total_tokens is None:
        if output_tokens is not None:
            total_tokens = input_tokens + output_tokens
        else:
            total_tokens = input_tokens

    if output_tokens is None:
        output_tokens = max(0, total_tokens - input_tokens)

    return {
        'input_tokens': max(0, int(input_tokens)),
        'output_tokens': max(0, int(output_tokens)),
        'total_tokens': max(0, int(total_tokens)),
    }


def extract_input_tokens(result, fallback_text: str = '') -> int:
    return extract_usage_metrics(result, fallback_text=fallback_text)['input_tokens']


def record_model_usage(
    model: str,
    input_tokens: int,
    output_tokens: int = 0,
    total_tokens: Optional[int] = None,
    operation: str = 'unspecified',
    duration_ms: Optional[int] = None,
) -> None:
    if not model:
        return
    now = now_brasilia()
    input_tokens = max(0, int(input_tokens or 0))
    output_tokens = max(0, int(output_tokens or 0))
    if total_tokens is None:
        total_tokens = input_tokens + output_tokens
    total_tokens = max(0, int(total_tokens))
    operation = (operation or 'unspecified').strip() or 'unspecified'
    duration_ms = None if duration_ms is None else max(0, int(duration_ms))

    with _lock:
        queue = _events_by_model[model]
        queue.append((now, input_tokens, output_tokens, total_tokens, operation))
        _prune(queue, now)

        event = {
            'timestamp': now.isoformat(),
            'model': model,
            'operation': operation,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': total_tokens,
        }
        if duration_ms is not None:
            event['duration_ms'] = duration_ms
        with open(_usage_log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')


def list_usage_history(limit: Optional[int] = None) -> list:
    with _lock:
        with open(_usage_log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

    if limit is not None:
        limit = max(1, min(int(limit), 50000))
        lines = lines[-limit:]

    history = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            history.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    history.reverse()
    return history


def _prune(queue: Deque[Event], now: datetime) -> None:
    day_ago = now - timedelta(days=1)
    while queue and queue[0][0] < day_ago:
        queue.popleft()


def _sum_window(queue: Deque[Event], since: datetime) -> Tuple[int, int, int, int]:
    requests = 0
    input_tokens_sum = 0
    output_tokens_sum = 0
    total_tokens_sum = 0
    for ts, input_tokens, output_tokens, total_tokens, _operation in queue:
        if ts >= since:
            requests += 1
            input_tokens_sum += input_tokens
            output_tokens_sum += output_tokens
            total_tokens_sum += total_tokens
    return requests, input_tokens_sum, output_tokens_sum, total_tokens_sum


def _operations_window(queue: Deque[Event], since: datetime) -> Dict[str, Dict[str, int]]:
    by_operation: Dict[str, Dict[str, int]] = {}
    for ts, input_tokens, output_tokens, total_tokens, operation in queue:
        if ts < since:
            continue
        item = by_operation.setdefault(
            operation,
            {
                'requests': 0,
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
            },
        )
        item['requests'] += 1
        item['input_tokens'] += input_tokens
        item['output_tokens'] += output_tokens
        item['total_tokens'] += total_tokens
    return by_operation


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


def get_usage_snapshot(
    additional_models: Optional[list] = None,
    include_history: bool = False,
    history_limit: Optional[int] = None,
) -> Dict:
    now = now_brasilia()
    minute_ago = now - timedelta(minutes=1)
    day_ago = now - timedelta(days=1)

    with _lock:
        tracked_models = set(_events_by_model.keys())
        if additional_models:
            tracked_models.update([m for m in additional_models if m])

        models_payload = []
        global_operations_last_minute: Dict[str, Dict[str, int]] = {}
        global_operations_last_day: Dict[str, Dict[str, int]] = {}
        for model in sorted(tracked_models):
            queue = _events_by_model.get(model, deque())
            _prune(queue, now)

            rpm_current, tpm_input_current, tpm_output_current, tpm_total_current = _sum_window(queue, minute_ago)
            rpd_current, rpd_input_tokens, rpd_output_tokens, rpd_total_tokens = _sum_window(queue, day_ago)
            model_operations_last_minute = _operations_window(queue, minute_ago)
            model_operations_last_day = _operations_window(queue, day_ago)

            for operation, values in model_operations_last_minute.items():
                acc = global_operations_last_minute.setdefault(
                    operation,
                    {
                        'requests': 0,
                        'input_tokens': 0,
                        'output_tokens': 0,
                        'total_tokens': 0,
                    },
                )
                acc['requests'] += values['requests']
                acc['input_tokens'] += values['input_tokens']
                acc['output_tokens'] += values['output_tokens']
                acc['total_tokens'] += values['total_tokens']

            for operation, values in model_operations_last_day.items():
                acc = global_operations_last_day.setdefault(
                    operation,
                    {
                        'requests': 0,
                        'input_tokens': 0,
                        'output_tokens': 0,
                        'total_tokens': 0,
                    },
                )
                acc['requests'] += values['requests']
                acc['input_tokens'] += values['input_tokens']
                acc['output_tokens'] += values['output_tokens']
                acc['total_tokens'] += values['total_tokens']

            limits = {
                'rpm': _resolve_limit(model, 'RPM'),
                'tpm': _resolve_limit(model, 'TPM'),
                'rpd': _resolve_limit(model, 'RPD'),
            }

            utilization = {
                'rpm_percent': _percent(rpm_current, limits['rpm']),
                'tpm_percent': _percent(tpm_input_current, limits['tpm']),
                'rpd_percent': _percent(rpd_current, limits['rpd']),
            }

            models_payload.append(
                {
                    'model': model,
                    'current': {
                        'rpm': rpm_current,
                        'tpm': tpm_input_current,
                        'tpm_input_tokens': tpm_input_current,
                        'tpm_output_tokens': tpm_output_current,
                        'tpm_total_tokens': tpm_total_current,
                        'rpd': rpd_current,
                        'rpd_input_tokens': rpd_input_tokens,
                        'rpd_output_tokens': rpd_output_tokens,
                        'rpd_total_tokens': rpd_total_tokens,
                    },
                    'limits': limits,
                    'utilization': utilization,
                    'operations_last_minute': model_operations_last_minute,
                    'operations_last_day': model_operations_last_day,
                    'status': _status_from_utilization(
                        utilization['rpm_percent'],
                        utilization['tpm_percent'],
                        utilization['rpd_percent'],
                    ),
                }
            )

    payload = {
        'generated_at': now.isoformat(),
        'models': models_payload,
        'global_operations_last_minute': global_operations_last_minute,
        'global_operations_last_day': global_operations_last_day,
        'notes': {
            'tpm_definition': 'TPM calculado com tokens de entrada no último minuto',
            'limits_source': 'Variáveis de ambiente GOOGLE_RATE_LIMIT_*',
            'token_measurement': 'input/output/total coletados de usage_metadata quando disponível; fallback por estimativa para entrada',
            'retention': 'Métricas em memória (janela de até 24h), reiniciam quando o backend reinicia',
            'history_persistence': f'Logs append-only persistidos em {_usage_log_path}',
        },
    }

    if include_history:
        payload['history'] = list_usage_history(limit=history_limit)

    return payload
