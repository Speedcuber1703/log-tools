"""Генерация standalone HTML-отчёта по логам.

Создаёт самодостаточный HTML-файл со встроенными CSS и JS,
не требующий работающего Django-сервера для просмотра.
"""
from __future__ import annotations

import json
import os
import tempfile
import webbrowser
from typing import Any


def generate_report_html(logs: list, title: str = "Log Tools Report") -> str:
    """Генерирует HTML-отчёт из списка логов.

    Args:
        logs: Список ``RequestLog`` для включения в отчёт.
        title: Заголовок отчёта.

    Returns:
        Строка с HTML-кодом отчёта.
    """
    from ._serialization import detect_n_plus_one

    logs_data = []
    n_plus_one_all = []

    for log in logs:
        np1 = detect_n_plus_one(log.entries)
        n_plus_one_all.extend(np1)

        logs_data.append({
            "method": log.method,
            "path": log.path,
            "status_code": log.status_code,
            "elapsed_ms": round(log.elapsed_ms, 2),
            "timestamp": log.timestamp,
            "summary": log.summary,
            "entries": log.entries,
            "source": getattr(log, "source", "http"),
            "command_name": getattr(log, "command_name", None),
            "n_plus_one": np1,
        })

    total_sql = sum(log.summary.get("sql_count", 0) for log in logs)
    total_redis = sum(log.summary.get("redis_count", 0) for log in logs)
    total_elapsed = sum(log.elapsed_ms for log in logs)
    avg_elapsed = round(total_elapsed / len(logs), 1) if logs else 0

    seen_patterns = set()
    unique_n_plus_one = []
    for np1 in n_plus_one_all:
        key = (np1["table"], np1["count"])
        if key not in seen_patterns:
            seen_patterns.add(key)
            unique_n_plus_one.append(np1)

    logs_json = json.dumps(logs_data, ensure_ascii=False, indent=2)

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --bg-primary: #0f1219; --bg-secondary: #171c26; --bg-tertiary: #1e2433;
    --bg-hover: #252d3f; --border: #2a3242; --border-light: #222a38;
    --text-primary: #e2e8f0; --text-secondary: #94a3b8; --text-muted: #64748b;
    --blue: #60a5fa; --green: #4ade80; --yellow: #fbbf24; --red: #f87171;
    --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: var(--font-sans); background: var(--bg-primary); color: var(--text-primary); padding: 20px; }}
  h1 {{ font-size: 18px; margin-bottom: 16px; }}
  .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 8px; margin-bottom: 20px; }}
  .metric {{ background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; padding: 12px; }}
  .metric .label {{ font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }}
  .metric .value {{ font-size: 20px; font-weight: 700; margin-top: 4px; font-family: var(--font-mono); }}
  .metric.ok .value {{ color: var(--green); }}
  .metric.warn .value {{ color: var(--yellow); }}
  .metric.slow .value {{ color: var(--red); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 20px; }}
  th {{ text-align: left; padding: 10px 12px; background: var(--bg-tertiary); color: var(--text-secondary);
       border-bottom: 1px solid var(--border); font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid var(--border-light); }}
  tr:hover {{ background: var(--bg-hover); cursor: pointer; }}
  tr:nth-child(even) {{ background: rgba(22,27,34,0.5); }}
  .method {{ display: inline-block; font-weight: 600; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-family: var(--font-mono); }}
  .method.GET {{ background: rgba(74,222,128,0.12); color: var(--green); }}
  .method.POST {{ background: rgba(96,165,250,0.12); color: var(--blue); }}
  .method.PUT, .method.PATCH {{ background: rgba(251,191,36,0.12); color: var(--yellow); }}
  .method.DELETE {{ background: rgba(248,113,113,0.12); color: var(--red); }}
  .status {{ font-weight: 600; font-family: var(--font-mono); }}
  .status.s2xx {{ color: var(--green); }} .status.s4xx {{ color: var(--yellow); }} .status.s5xx {{ color: var(--red); }}
  .slow {{ color: var(--red); font-weight: 600; }}
  .time {{ font-family: var(--font-mono); font-size: 11px; color: var(--text-secondary); }}
  .path {{ font-family: var(--font-mono); font-size: 12px; }}
  .source-badge {{ display: inline-block; background: rgba(192,132,252,0.12); color: #c084fc;
                   padding: 1px 5px; border-radius: 3px; font-size: 9px; font-weight: 600; margin-left: 4px; }}
  .dup-badge {{ background: rgba(251,191,36,0.12); color: var(--yellow); padding: 1px 5px;
                border-radius: 3px; font-size: 9px; font-weight: 600; margin-left: 4px; }}
  .n1-badge {{ background: rgba(248,113,113,0.12); color: var(--red); padding: 1px 5px;
               border-radius: 3px; font-size: 9px; font-weight: 600; }}
  .detail {{ display: none; background: var(--bg-secondary); border: 1px solid var(--border);
             border-radius: 8px; padding: 16px; margin-bottom: 12px; }}
  .detail.open {{ display: block; }}
  .sql-block {{ background: var(--bg-primary); border: 1px solid var(--border-light); border-radius: 6px;
                padding: 10px 12px; font-family: var(--font-mono); font-size: 12px; line-height: 1.6;
                white-space: pre-wrap; word-break: break-all; margin-top: 6px; }}
  .sql-block .kw {{ color: var(--blue); font-weight: 500; }}
  .sql-block .str {{ color: var(--green); }}
  .sql-block .num {{ color: var(--yellow); }}
  .entry {{ background: var(--bg-primary); border-radius: 6px; padding: 10px 12px; font-size: 12px;
            border-left: 3px solid var(--border); margin-bottom: 4px; }}
  .entry.sql {{ border-left-color: var(--blue); }}
  .entry.redis {{ border-left-color: var(--yellow); }}
  .entry.timing {{ border-left-color: var(--green); }}
  .entry-header {{ display: flex; justify-content: space-between; margin-bottom: 4px; }}
  .entry-type {{ font-weight: 600; font-size: 10px; text-transform: uppercase; }}
  .entry-type.sql {{ color: var(--blue); }} .entry-type.redis {{ color: var(--yellow); }}
  .entry-dur {{ font-family: var(--font-mono); font-size: 11px; color: var(--text-secondary); }}
</style>
</head>
<body>
<h1>{title}</h1>

<div class="metrics">
  <div class="metric ok"><div class="label">Запросов</div><div class="value">{len(logs)}</div></div>
  <div class="metric"><div class="label">SQL</div><div class="value">{total_sql}</div></div>
  <div class="metric"><div class="label">Redis</div><div class="value">{total_redis}</div></div>
  <div class="metric {'ok' if avg_elapsed < 50 else 'warn' if avg_elapsed < 100 else 'slow'}">
    <div class="label">Среднее</div><div class="value">{avg_elapsed}мс</div></div>
  <div class="metric {'warn' if unique_n_plus_one else 'ok'}">
    <div class="label">N+1</div><div class="value">{len(unique_n_plus_one)}</div></div>
</div>

<table>
<thead><tr>
  <th>Метод</th><th>Путь</th><th>Статус</th><th>Время</th><th>SQL</th><th>Redis</th><th>Записей</th>
</tr></thead>
<tbody id="log-table"></tbody>
</table>

<div id="detail-container"></div>

<script>
const LOGS = {logs_json};

const table = document.getElementById('log-table');
LOGS.forEach((log, i) => {{
  const tr = document.createElement('tr');
  tr.onclick = () => toggleDetail(i);
  const statusClass = log.status_code < 300 ? 's2xx' : log.status_code < 500 ? 's4xx' : 's5xx';
  const methodClass = log.method;
  const dupCount = Object.values(log.summary.sql_duplicates || {{}}).filter(v => v > 1).length;
  const n1Count = log.n_plus_one.length;
  const sourceBadge = log.source !== 'http' ?
    `<span class="source-badge">${{log.source}}</span>` : '';
  const commandBadge = log.command_name ?
    `<span class="source-badge">${{log.command_name}}</span>` : '';
  const dupBadge = dupCount > 0 ? `<span class="dup-badge">${{dupCount}} дублей</span>` : '';
  const n1Badge = n1Count > 0 ? `<span class="n1-badge">N+1: ${{n1Count}}</span>` : '';

  tr.innerHTML = `
    <td><span class="method ${{methodClass}}">${{log.method}}</span>${{sourceBadge}}${{commandBadge}}</td>
    <td><span class="path">${{log.path}}</span></td>
    <td><span class="status ${{statusClass}}">${{log.status_code}}</span></td>
    <td><span class="time ${{log.elapsed_ms > 100 ? 'slow' : ''}}">${{log.elapsed_ms}}мс</span></td>
    <td>${{log.summary.sql_count}}${{dupBadge}}</td>
    <td>${{log.summary.redis_count}}</td>
    <td>${{log.summary.total_entries}}${{n1Badge}}</td>
  `;
  table.appendChild(tr);

  const detail = document.createElement('div');
  detail.className = 'detail';
  detail.id = 'detail-' + i;
  let html = '';

  if (log.n_plus_one.length > 0) {{
    html += '<div style="margin-bottom:12px;color:var(--red);font-weight:600">&#9888; N+1 паттерны</div>';
    log.n_plus_one.forEach(np => {{
      html += `<div class="entry" style="border-left-color:var(--red)">
        <div class="entry-header"><span class="entry-type" style="color:var(--red)">N+1: ${{np.table}}</span>
        <span class="entry-dur">${{np.count}}x (${{np.total_ms}}мс)</span></div></div>`;
    }});
  }}

  log.entries.forEach(e => {{
    const dur = e.duration_ms !== null ? `<span class="entry-dur">${{e.duration_ms.toFixed(2)}}мс</span>` : '';
    const dupNorm = e.data.normalized_sql || '';
    const dupCount = (log.summary.sql_duplicates || {{}})[dupNorm] || 1;
    const dupBadge = dupCount > 1 ? ` <span class="dup-badge">x${{dupCount}}</span>` : '';
    html += `<div class="entry ${{e.type}}">
      <div class="entry-header"><span class="entry-type ${{e.type}}">${{e.type.toUpperCase()}}</span>${{dur}}</div>`;
    if (e.type === 'sql') {{
      html += `<div class="sql-block">${{highlightSql(e.data.sql)}}</div>${{dupBadge}}`;
    }} else if (e.type === 'redis') {{
      html += `<div style="color:var(--yellow);font-family:var(--font-mono);margin-top:4px">${{e.data.command}} ${{JSON.stringify(e.data.args)}}</div>`;
    }} else if (e.type === 'timing') {{
      html += `<span style="color:var(--text-secondary)">${{e.data.label}}</span>`;
    }} else if (e.type === 'log') {{
      html += `<span style="color:var(--text-secondary)">${{e.data.message}}</span>`;
    }}
    html += '</div>';
  }});

  detail.innerHTML = html;
  document.getElementById('detail-container').appendChild(detail);
}});

function toggleDetail(i) {{
  const d = document.getElementById('detail-' + i);
  const wasOpen = d.classList.contains('open');
  document.querySelectorAll('.detail').forEach(el => el.classList.remove('open'));
  if (!wasOpen) d.classList.add('open');
}}

function highlightSql(sql) {{
  if (!sql) return '';
  let h = sql.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const kws = ['SELECT','FROM','WHERE','AND','OR','IN','NOT','NULL','IS','INSERT','INTO',
    'VALUES','UPDATE','SET','DELETE','JOIN','LEFT','RIGHT','INNER','ON','AS','ORDER','BY',
    'GROUP','HAVING','LIMIT','OFFSET','COUNT','SUM','AVG','MIN','MAX','DISTINCT','ASC','DESC',
    'TRUE','FALSE','CASE','WHEN','THEN','ELSE','END','BETWEEN','LIKE','EXISTS'];
  kws.forEach(kw => {{ h = h.replace(new RegExp('\\\\b' + kw + '\\\\b', 'gi'), '<span class="kw">' + kw + '</span>'); }});
  h = h.replace(/'([^']*)'/g, '<span class="str">\\'$1\\'</span>');
  h = h.replace(/\\b(\\d+\\.?\\d*)\\b/g, '<span class="num">$1</span>');
  return h;
}}
</script>
</body>
</html>"""


def open_report(logs: list, title: str = "Log Tools Report") -> str:
    """Генерирует HTML-отчёт и открывает его в браузере.

    Args:
        logs: Список ``RequestLog`` для включения в отчёт.
        title: Заголовок отчёта.

    Returns:
        Путь к созданному HTML-файлу.
    """
    html = generate_report_html(logs, title)

    tmp_dir = tempfile.mkdtemp(prefix="log_tools_")
    file_path = os.path.join(tmp_dir, "report.html")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html)

    webbrowser.open(f"file://{file_path}")
    return file_path
