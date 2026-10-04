"""Browser history as a search source: Chromium family and Firefox.

Opt-in only (see the `history*` settings). History files are copied into the
user's private cache because browsers lock them while running, then searched
locally. Nothing is uploaded and nothing outside the copies is written.
"""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import glob

HOME = str(Path.home())
CHROMIUM_EPOCH = 11644473600  # seconds between 1601-01-01 and 1970-01-01

# id -> (display name, engine, profile roots, desktop ids used to spot the default)
_CHROMIUM = {
    'chromium': ('Chromium',
                 ['~/.config/chromium', '~/snap/chromium/common/chromium',
                  '~/.var/app/org.chromium.Chromium/config/chromium'],
                 ['chromium.desktop', 'chromium_chromium.desktop', 'org.chromium.Chromium.desktop']),
    'chrome': ('Google Chrome',
               ['~/.config/google-chrome', '~/.var/app/com.google.Chrome/config/google-chrome'],
               ['google-chrome.desktop', 'com.google.Chrome.desktop']),
    'brave': ('Brave',
              ['~/.config/BraveSoftware/Brave-Browser',
               '~/.var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser'],
              ['brave-browser.desktop', 'com.brave.Browser.desktop']),
    'edge': ('Microsoft Edge', ['~/.config/microsoft-edge'], ['microsoft-edge.desktop']),
    'vivaldi': ('Vivaldi', ['~/.config/vivaldi'], ['vivaldi-stable.desktop']),
}
_FIREFOX = ('Firefox',
            ['~/.mozilla/firefox', '~/snap/firefox/common/.mozilla/firefox',
             '~/.var/app/org.mozilla.firefox/.mozilla/firefox'],
            ['firefox.desktop', 'firefox_firefox.desktop', 'org.mozilla.firefox.desktop'])


def _patterns(browser_id):
    if browser_id == 'firefox':
        return [f'{root}/*/places.sqlite' for root in _FIREFOX[1]]
    roots = _CHROMIUM[browser_id][1]
    return [p for root in roots for p in (f'{root}/Default/History', f'{root}/Profile */History')]


def browser_ids():
    return ['firefox', *_CHROMIUM]


def browser_name(browser_id):
    return _FIREFOX[0] if browser_id == 'firefox' else _CHROMIUM[browser_id][0]


def history_files(browser_id):
    found = []
    for pattern in _patterns(browser_id):
        for path in sorted(glob.glob(os.path.expanduser(pattern))):
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                found.append(path)
    return found


def detected():
    """Browsers that already have history on this account."""
    return [{'id': b, 'name': browser_name(b), 'profiles': len(files)}
            for b in browser_ids() if (files := history_files(b))]


def default_browser():
    try:
        desktop = subprocess.run(['xdg-settings', 'get', 'default-web-browser'], capture_output=True,
                                 text=True, timeout=2, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    for browser_id in browser_ids():
        ids = _FIREFOX[2] if browser_id == 'firefox' else _CHROMIUM[browser_id][2]
        if desktop in ids:
            return browser_id
    return None


def _history_dir(directory):
    target = Path(directory) / 'history'
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.chmod(0o700)
    return target


def _copy_name(browser_id, source):
    return f'{browser_id}-{hashlib.sha1(source.encode()).hexdigest()[:10]}.sqlite'


def _sidecars(path):
    return [path + suffix for suffix in ('-wal', '-shm') if os.path.exists(path + suffix)]


def refresh_history(directory, browsers, max_age=0):
    """Copy selected browsers' history into the private cache when it changed."""
    target = _history_dir(directory)
    wanted = set()
    for browser_id in browsers:
        if browser_id not in browser_ids():
            continue
        for source in history_files(browser_id):
            copy = target / _copy_name(browser_id, source)
            wanted.add(copy.name)
            parts = [source, *_sidecars(source)]
            try:
                newest = max(os.path.getmtime(p) for p in parts)
                if copy.exists() and copy.stat().st_mtime >= newest:
                    continue
                if copy.exists() and max_age and (os.path.getmtime(copy) + max_age) > time.time():
                    continue
                temporary = target / (copy.name + '.new')
                for old in (temporary, *map(Path, _sidecars(str(temporary)))):
                    old.unlink(missing_ok=True)
                shutil.copyfile(source, temporary)
                for side in _sidecars(source):
                    shutil.copyfile(side, str(temporary) + side[len(source):])
                for part in (temporary, *map(Path, _sidecars(str(temporary)))):
                    part.chmod(0o600)
                for part in (temporary, *map(Path, _sidecars(str(temporary)))):
                    part.replace(str(copy) + str(part)[len(str(temporary)):])
            except OSError:
                continue
    # Drop copies for browsers or profiles that are no longer selected.
    for stale in target.iterdir():
        base = stale.name.split('.sqlite')[0] + '.sqlite'
        if base not in wanted:
            stale.unlink(missing_ok=True)


def clear_history(directory):
    target = Path(directory) / 'history'
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)


def _like(word):
    return '%' + word.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


def _query_copy(path, browser_id, words, limit):
    chromium = browser_id != 'firefox'
    table, time_column = ('urls', 'last_visit_time') if chromium else ('moz_places', 'last_visit_date')
    clause = ' AND '.join("(cf(title) LIKE ? ESCAPE '\\' OR cf(url) LIKE ? ESCAPE '\\')" for _ in words)
    params = [like for word in words for like in (_like(word), _like(word))]
    sql = (f"SELECT url, title, {time_column} FROM {table} WHERE {time_column} > 0 "
           f"AND (url LIKE 'http://%' OR url LIKE 'https://%') AND {clause} "
           f"ORDER BY {time_column} DESC LIMIT ?")
    with closing(sqlite3.connect(path)) as db:
        db.create_function('cf', 1, lambda text: text.casefold() if text else '', deterministic=True)
        rows = db.execute(sql, (*params, limit)).fetchall()
    for url, title, stamp in rows:
        seconds = stamp / 1e6 - (CHROMIUM_EPOCH if chromium else 0)
        yield url, title or '', seconds


def search_history(directory, query, browsers, limit):
    words = [word.casefold() for word in query.split() if word]
    if not words:
        return [], ''
    target = Path(directory) / 'history'
    found = {}
    unavailable = False
    for browser_id in browsers:
        for source in history_files(browser_id):
            copy = target / _copy_name(browser_id, source)
            if not copy.exists():
                unavailable = True
                continue
            try:
                for url, title, seconds in _query_copy(str(copy), browser_id, words, limit * 3):
                    if url not in found or found[url][0] < seconds:
                        found[url] = (seconds, title, browser_id)
            except sqlite3.Error:
                unavailable = True
    ordered = sorted(found.items(), key=lambda item: item[1][0], reverse=True)[:limit]
    results = [{'kind': 'history', 'title': title or url,
                'detail': f'{url} · {browser_name(browser_id)}', 'uri': url,
                'icon': 'web-browser-symbolic'} for url, (_, title, browser_id) in ordered]
    notice = 'Browser history is still being copied. Try again in a moment.' if unavailable and not results else ''
    return results, notice
