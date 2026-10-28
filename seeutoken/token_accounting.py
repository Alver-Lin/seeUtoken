"""Project canonical, cache-exclusive usage into the selected display basis.

Never change input/output/cache counters or mutate the source cache. Applying
the projection repeatedly, including after reloading a disk cache, is safe.
"""
from __future__ import annotations

from copy import deepcopy

from .heatmap import build_year_grid


def token_total(item: dict, include_cache: bool = False) -> int:
    if 'input' not in item and 'output' not in item:
        return int(item.get('tokens') or 0)
    return int(item.get('input') or 0) + int(item.get('output') or 0) + (
        int(item.get('cache') or 0) if include_cache else 0)


def project_heatmap(heatmap: dict, include_cache: bool) -> dict:
    days = {date: {**day, 'tokens': token_total(day, include_cache)}
            for date, day in (heatmap.get('days') or {}).items()}
    return {**build_year_grid(heatmap['year'], days), 'includeCachedTokens': include_cache}


def project_usage(data: dict, include_cache: bool) -> dict:
    result = deepcopy(data)
    result['includeCachedTokens'] = include_cache
    result['tokenBasis'] = 'input_output_cache' if include_cache else 'uncached_input_output'
    for period in (result.get('periods') or {}).values():
        period['tokens'] = token_total(period, include_cache)
        period['processedTokens'] = token_total(period, True)
    for rows in (result.get('models') or {}).values():
        for item in rows:
            item['tokens'] = token_total(item, include_cache)
            item['processedTokens'] = token_total(item, True)
        total = sum(item['tokens'] for item in rows) or 1
        for item in rows:
            item['percent'] = item['tokens'] / total * 100
        rows.sort(key=lambda item: item['tokens'], reverse=True)
    for item in result.get('events') or []:
        item['tokens'] = token_total(item, include_cache)
        item['processedTokens'] = token_total(item, True)
    if result.get('periods'):
        result['usageTokens'] = {
            period: item['tokens'] for period, item in result['periods'].items()
            if not result.get('partial') or token_total(item, True) > 0 or
            item.get('calls') is not None or float(item.get('cost') or 0) > 0
        }
    if isinstance(result.get('heatmap'), dict):
        result['heatmap'] = project_heatmap(result['heatmap'], include_cache)
    return result
