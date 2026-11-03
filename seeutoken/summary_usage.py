"""Combine provider summaries without counting their limited detail rows as totals."""
from copy import deepcopy

from .heatmap import aggregate_days_from_events, build_year_grid
from .token_accounting import project_usage, token_total

PERIODS = ('today', 'week', 'month', 'all')
COUNTERS = ('input', 'output', 'cache', 'calls')


def _add_usage(target: dict, source: dict) -> None:
    for field in ('input', 'output', 'cache'):
        target[field] += int(source.get(field) or 0)
    calls = source.get('calls')
    if calls is None:
        target['calls'] = None
    elif target['calls'] is not None:
        target['calls'] += int(calls)
    target['knownCalls'] += int(calls or 0)


def combine_usage(sources: dict[str, dict], year: int, include_cache: bool = False) -> dict:
    periods = {key: {**dict.fromkeys(COUNTERS, 0), 'knownCalls': 0} for key in PERIODS}
    grouped = {key: {} for key in PERIODS}
    events, days = [], {}
    for provider, data in sources.items():
        if not data or data.get('demo'):
            continue
        for period in PERIODS:
            source_period = (data.get('periods') or {}).get(period)
            if source_period is not None:
                _add_usage(periods[period], source_period)
            for model in data.get('models', {}).get(period) or []:
                name = model.get('model') or '未知模型'
                row = grouped[period].setdefault(name, {'model': name, 'providers': [], 'knownCalls': 0, **dict.fromkeys(COUNTERS, 0)})
                if provider not in row['providers']:
                    row['providers'].append(provider)
                _add_usage(row, model)
        for index, event in enumerate(data.get('events') or []):
            events.append({**deepcopy(event), 'provider': provider,
                           'id': f"{provider}:{event.get('id') or index}"})
        source_days = (data.get('heatmap') or {}).get('days')
        if source_days is None:
            source_days = aggregate_days_from_events(data.get('events') or [])
        for date, day in source_days.items():
            bucket = days.setdefault(date, {**dict.fromkeys(COUNTERS, 0), 'tokens': 0})
            for field in COUNTERS:
                bucket[field] += int(day.get(field) or 0)
            # A legacy heatmap can contain only total tokens; retain that total.
            bucket['tokens'] += token_total(day, include_cache)
    # The projected totals above also handle legacy days lacking component counters.
    heatmap = build_year_grid(year, days)
    result = project_usage({'periods': periods, 'models': {
        period: list(rows.values()) for period, rows in grouped.items()},
        'events': sorted(events, key=lambda event: event.get('time') or 0, reverse=True)}, include_cache)
    result['heatmap'] = {**heatmap, 'includeCachedTokens': include_cache}
    return result
