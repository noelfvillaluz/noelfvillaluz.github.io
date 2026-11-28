#!/usr/bin/env python3
"""Release due publications from a private repository into branch-deployed Pages."""
import argparse
import html
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

START = '<!-- AUTO_PUBLISHED_ARTICLES_START -->'
END = '<!-- AUTO_PUBLISHED_ARTICLES_END -->'
DUBAI = ZoneInfo('Asia/Dubai')


def safe_file(base: Path, rel: str) -> Path:
    p = Path(rel)
    if p.is_absolute() or not p.parts or any(x in ('.', '..') for x in p.parts):
        raise ValueError(f'Unsafe filename: {rel}')
    resolved = (base / p).resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise ValueError(f'Unsafe file path: {rel}')
    return resolved


def render_card(entry: dict) -> str:
    esc = lambda s: html.escape(str(s), quote=True)
    date = datetime.fromisoformat(entry['publish_at']).astimezone(DUBAI)
    image = f'<img src="{esc(entry["image"])}" alt="{esc(entry["title"])}" loading="lazy" style="width:100%;height:auto;border-radius:8px;margin-top:18px">' if entry.get('image') else ''
    return f"""<!-- AUTO ARTICLE: {esc(entry['id'])} -->
<article class="publication-card" data-category="{esc(entry['category'])}">
  <div class="publication-meta"><span>{esc(entry['id'])}</span><span>{date:%d %b %Y}</span></div>
  <h3>{esc(entry['title'])}</h3>
  <span class="publication-category">{esc(entry['category'])}</span>
  {image}
  <p class="publication-summary">{esc(entry['summary'])}</p>
  <a class="publication-btn" href="{esc(entry['html'])}">Read Full Article</a>
</article>"""


def publish(site: Path, staging: Path, now: datetime) -> None:
    manifest = json.loads((staging / 'schedule.json').read_text(encoding='utf-8'))
    entries = manifest['articles']
    ids = [a['id'] for a in entries]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate article IDs in schedule.json')
    due = []
    for entry in entries:
        publish_at = datetime.fromisoformat(entry['publish_at'])
        if publish_at.tzinfo is None:
            raise ValueError(f'Missing timezone offset for {entry["id"]}')
        if now < publish_at:
            continue
        due.append(entry)
    # Validate all source files before making any modifications.
    transfers = []
    for entry in due:
        directory = safe_file(staging, entry['folder'])
        for filename in entry['files']:
            if '/' in filename or '\\' in filename or filename in ('.', '..'):
                raise ValueError(f'Only root-level published filenames supported: {filename}')
            src = safe_file(directory, filename)
            if not src.is_file():
                raise FileNotFoundError(f'Missing publication file: {src}')
            transfers.append((src, site / filename))
        if entry['html'] not in entry['files']:
            raise ValueError(f'HTML page missing from files list: {entry["id"]}')
        if entry.get('image') and entry['image'] not in entry['files']:
            raise ValueError(f'Image missing from files list: {entry["id"]}')
    page = site / 'Articles.html'
    contents = page.read_text(encoding='utf-8')
    if contents.count(START) != 1 or contents.count(END) != 1:
        raise ValueError('Expected exactly one start and end marker in Articles.html')
    cards = '\n\n'.join(render_card(a) for a in sorted(due, key=lambda a: a['publish_at'], reverse=True))
    # Protect existing public files against accidental overwrites.
    for src, dst in transfers:
        if dst.exists() and dst.read_bytes() != src.read_bytes():
            raise ValueError(f'Published file already exists with different content: {dst.name}')
    for src, dst in transfers:
        if not dst.exists():
            dst.write_bytes(src.read_bytes())
            print(f'Published file: {dst.name}')
    before, rest = contents.split(START, 1)
    _, after = rest.split(END, 1)
    updated = before + START + '\n' + cards + '\n' + END + after
    if updated != contents:
        page.write_text(updated, encoding='utf-8')
    print(f'As of {now.isoformat()}: {len(due)} articles due; publication listing updated.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--staging', type=Path, required=True)
    parser.add_argument('--now', default=None, help='Optional test date, e.g. 2026-11-28T09:00:00+04:00')
    args = parser.parse_args()
    current = datetime.fromisoformat(args.now) if args.now else datetime.now(DUBAI)
    if current.tzinfo is None:
        raise ValueError('--now must include a timezone offset')
    publish(args.site.resolve(), args.staging.resolve(), current)
