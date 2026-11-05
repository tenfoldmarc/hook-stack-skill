#!/usr/bin/env python3
"""Rank the hooks of a launch from the numbers the Meta Ads connector returned. Standard library only.

  rank_hooks.py <project_dir>

Reads <project_dir>/work/results_raw.json, which Claude writes from the connector's reporting tool:
  {"since": "2026-11-05", "until": "2026-11-08", "result_label": "purchases",
   "rows": [{"id": "H01", "ad_id": "...", "spend": 41.20, "impressions": 3810, "video_3s_views": 1290,
             "thruplays": 402, "link_clicks": 61, "results": 3}, ...]}
(any field Meta did not return can be left out). Prints the table, best hook first, and writes work/results.json.
hook rate = 3-second video views / impressions: how well the hook stops the scroll.
hold rate = ThruPlays / 3-second views: how well the body keeps them after the hook.
"""
import json
import os
import sys


def num(r, k):
    try:
        return float(r.get(k) or 0)
    except (TypeError, ValueError):
        return 0.0


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__.strip())
        return
    project = os.path.abspath(os.path.expanduser(sys.argv[1]))
    with open(os.path.join(project, 'work', 'results_raw.json'), encoding='utf-8') as f:
        raw = json.load(f)
    rows = []
    for r in raw['rows']:
        imp, v3, spend, res = num(r, 'impressions'), num(r, 'video_3s_views'), num(r, 'spend'), num(r, 'results')
        rows.append({'id': r['id'], 'spend': spend, 'impressions': imp,
                     'hook_rate': v3 / imp if imp else 0.0, 'hold_rate': num(r, 'thruplays') / v3 if v3 else 0.0,
                     'ctr': num(r, 'link_clicks') / imp if imp else 0.0, 'results': res,
                     'cost_per_result': spend / res if res else None})
    rows.sort(key=lambda r: (r['results'] == 0, r['cost_per_result'] or 0, -r['hook_rate']))
    label = raw.get('result_label', 'results')
    print(f'{raw.get("since", "")} to {raw.get("until", "")}')
    print(f'{"ad":<6}{"spend":>9}{"impr":>9}{"hook rate":>11}{"hold":>8}{"CTR":>8}{label:>12}{"cost each":>11}')
    for r in rows:
        cpr = f'{r["cost_per_result"]:.2f}' if r['cost_per_result'] else '-'
        print(f'{r["id"]:<6}{r["spend"]:>9.2f}{r["impressions"]:>9.0f}{r["hook_rate"]:>10.1%}{r["hold_rate"]:>8.1%}'
              f'{r["ctr"]:>8.2%}{r["results"]:>12.0f}{cpr:>11}')
    low = [r['id'] for r in rows if r['impressions'] < 1000]
    if low:
        print(f'note: {", ".join(low)} have under 1,000 impressions; too early to call')
    with open(os.path.join(project, 'work', 'results.json'), 'w', encoding='utf-8') as f:
        json.dump({**{k: raw.get(k) for k in ('since', 'until', 'result_label')}, 'rows': rows}, f, indent=1)


if __name__ == '__main__':
    main()
