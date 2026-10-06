"""Control Panel logic that needs no GTK: turn `noc` JSON into what the window shows.

The panel is a GUI for `noc`, not a second implementation (docs/control-panel-plan.md): every
number on screen comes from `noc status --json` and friends, so this module only formats it.
Kept free of PyGObject so the unit tests (and CI) can import it.
"""
import json
import os
import re
import subprocess
import urllib.request
from dataclasses import dataclass

NOC = '/usr/local/bin/noc'

LEVELS = ('ok', 'warn', 'info')


@dataclass
class Card:
    id: str
    title: str
    value: str
    detail: str = ''
    level: str = 'info'   # ok | warn | info: only drives the accent colour of the card
    page: str = ''        # sidebar page the card opens, '' when it is not clickable


def fmt_bytes(n):
    """Whole bytes as the largest sensible unit: 61300000000 -> '57.1 GB'."""
    value = float(n)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024 or unit == 'TB':
            return f'{value:.0f} {unit}' if unit == 'B' else f'{value:.1f} {unit}'
        value /= 1024


def fmt_age(seconds):
    """Seconds as a short age: 45 -> 'just now', 600 -> '10 minutes ago', 90000 -> '1 day ago'."""
    if seconds < 60:
        return 'just now'
    for size, name in ((86400, 'day'), (3600, 'hour'), (60, 'minute')):
        if seconds >= size:
            n = int(seconds // size)
            return f'{n} {name}{"" if n == 1 else "s"} ago'


def _updates_card(updates):
    apt, flatpak = updates.get('apt'), updates.get('flatpak')
    known = [n for n in (apt, flatpak) if n is not None]
    reboot = updates.get('reboot_required')
    if not known:
        value, level = 'Could not check', 'info'
        detail = 'No network, or the package lists are unavailable.'
    elif sum(known) == 0:
        value, level, detail = 'Up to date', 'ok', ''
    else:
        total = sum(known)
        value, level = f'{total} update{"" if total == 1 else "s"} available', 'warn'
        parts = [f'{n} {label}' for n, label in ((apt, 'system'), (flatpak, 'app')) if n]
        detail = ', '.join(parts)
        if None in (apt, flatpak):
            detail += ' (the rest could not be checked)'
    if reboot:
        level = 'warn'
        detail = (detail + '. ' if detail else '') + 'Restart needed to finish an update.'
    return Card('updates', 'Updates', value, detail, level, 'updates')


def _ollama_card(ollama):
    if not ollama.get('running'):
        return Card('ollama', 'Local AI', 'Not running',
                    'Ollama is starting, or is not installed yet. Local AI works offline once it is.',
                    'warn', 'models')
    n = ollama.get('models', 0)
    detail = f'Default model: {ollama.get("default_model")}'
    return Card('ollama', 'Local AI', 'Ollama running', f'{n} model{"" if n == 1 else "s"} installed. {detail}',
                'ok', 'models')


def _gpu_card(gpu):
    if gpu is None:
        return Card('gpu', 'Graphics', 'Not checked', 'GPU detection is unavailable.', 'info', 'hardware')
    gpus = gpu.get('gpus') or []
    if not gpus:
        return Card('gpu', 'Graphics', 'No GPU for AI', 'Local models run on the CPU.', 'info', 'hardware')
    extra = f' (+{len(gpus) - 1} more)' if len(gpus) > 1 else ''
    return Card('gpu', 'Graphics', gpus[0].get('name', 'GPU') + extra,
                'NVIDIA / AMD detected', 'ok', 'hardware')


def _hermes_card(hermes):
    mode = hermes.get('mode')
    if not hermes.get('installed') and mode is None:
        return Card('hermes', 'Hermes', 'Not installed', 'Hermes Desktop is set up on first boot.', 'info', 'privacy')
    if mode == 'local':
        return Card('hermes', 'Hermes', 'Local only', 'Prompts stay on this computer.', 'ok', 'privacy')
    if mode == 'other':
        return Card('hermes', 'Hermes', 'Your own provider', 'Configured in Hermes itself.', 'info', 'privacy')
    # The free tier is Nous Research's cloud: never describe it as local (AGENTS.md).
    return Card('hermes', 'Hermes', 'Nous free tier',
                'Cloud service: prompts leave this computer.', 'warn', 'privacy')


def cards(status):
    """The Overview cards, in display order, from a `noc status` document."""
    disk = status.get('disk') or {}
    free, total = disk.get('root_free_bytes'), disk.get('root_total_bytes')
    low = bool(total) and free / total < 0.10
    age = status.get('search_index_age_seconds')
    return [
        Card('version', 'NoctraOS', f'Version {status.get("version", "?")}', status.get('os') or '', 'ok', 'about'),
        _updates_card(status.get('updates') or {}),
        _ollama_card(status.get('ollama') or {}),
        _gpu_card(status.get('gpu')),
        Card('disk', 'Disk', f'{fmt_bytes(free)} free' if free is not None else 'Unknown',
             f'of {fmt_bytes(total)}. Low space slows updates and models.' if total and low
             else (f'of {fmt_bytes(total)}' if total else ''),
             'warn' if low else 'ok', 'hardware'),
        _hermes_card(status.get('hermes') or {}),
        Card('search', 'Search index',
             'Not built yet' if age is None else f'Updated {fmt_age(age)}',
             'Super+Space finds files once the index exists.' if age is None else '',
             'info' if age is None else 'ok'),
    ]


def diagnostics_text(status, kernel=''):
    """Plain text for a bug report: no secrets, no file names, no prompts."""
    lines = ['NoctraOS diagnostics',
             f'version: {status.get("version")}',
             f'os: {status.get("os")}',
             f'kernel: {kernel or "unknown"}',
             f'ram: {status.get("ram_gb")} GB']
    disk = status.get('disk') or {}
    if disk:
        lines.append(f'disk: {fmt_bytes(disk["root_free_bytes"])} free of {fmt_bytes(disk["root_total_bytes"])}')
    ollama = status.get('ollama') or {}
    lines.append(f'ollama: {"running " + str(ollama.get("version")) if ollama.get("running") else "not running"}, '
                 f'{ollama.get("models", 0)} models, default {ollama.get("default_model")}')
    gpus = ((status.get('gpu') or {}).get('gpus')) or []
    lines.append('gpu: ' + ('; '.join(g.get('name', '?') for g in gpus) if gpus else 'none'))
    lines.append(f'hermes: {(status.get("hermes") or {}).get("mode") or "not installed"}')
    updates = status.get('updates') or {}
    lines.append(f'updates: apt {updates.get("apt")}, flatpak {updates.get("flatpak")}, '
                 f'reboot needed {updates.get("reboot_required")}')
    return '\n'.join(lines) + '\n'


def noc_json(*args, timeout=90):
    """Run `noc <args>` and parse its JSON. Returns None when noc is missing, fails or prints junk,
    so a page can show its "not ready yet" state instead of raising."""
    try:
        out = subprocess.run([NOC, *args], capture_output=True, text=True, timeout=timeout)
        return json.loads(out.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


# ---- Health ----------------------------------------------------------------------------------

HERMES = '/usr/local/bin/noctraos-hermes'
SEVERITY = {'fail': 0, 'warn': 1, 'info': 2, 'ok': 3}

# Fixes the panel can run without root. "module:<name>" needs the privileged helper (phase 4), so
# it has no entry here and its row simply shows no button: never fall back to `sudo` in a GUI.
FIXES = {'hermes:install': [HERMES, 'install']}


def sort_rows(rows):
    """Problems first, in the order `noc doctor` found them within each severity."""
    return sorted(rows, key=lambda r: SEVERITY.get(r.get('status'), 2))


def health_headline(rows):
    """(text, level) for the top of the Health page."""
    bad = sum(1 for r in rows if r.get('status') == 'fail')
    warn = sum(1 for r in rows if r.get('status') == 'warn')
    if bad:
        return (f'{bad} problem needs attention' if bad == 1 else f'{bad} problems need attention'), 'fail'
    if warn:
        return (f'{warn} thing could be better' if warn == 1 else f'{warn} things could be better'), 'warn'
    return 'Everything checks out', 'ok'


def fix_command(fix):
    """The argv for a doctor row's `fix`, or None when the panel cannot run it."""
    return FIXES.get(fix)


def report_text(rows, kernel=''):
    """Plain text of the whole check for a bug report: one line per row, no secrets."""
    marks = {'ok': 'OK  ', 'warn': 'WARN', 'fail': 'FAIL', 'info': 'INFO'}
    lines = ['NoctraOS health report', f'kernel: {kernel or "unknown"}']
    for r in rows:
        detail = f': {r["detail"]}' if r.get('detail') else ''
        lines.append(f'[{marks.get(r.get("status"), "INFO")}] {r.get("label")}{detail}')
    return '\n'.join(lines) + '\n'


# ---- AI models -------------------------------------------------------------------------------

OLLAMA_URL = os.environ.get('NOC_OLLAMA_URL', 'http://127.0.0.1:11434')
# Same rule as `noc models default`: letters, digits and . _ : / - only.
_MODEL_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:/-]*$')

FIT_TEXT = {'gpu': 'Runs on your GPU', 'cpu': 'Runs on the CPU (slower)', 'no': 'May not fit in memory'}


def valid_model_name(name):
    return bool(_MODEL_NAME.match(name or ''))


def same_model(a, b):
    """Ollama lists "name:latest" for a model pulled as "name"."""
    strip = lambda n: n[:-7] if n.endswith(':latest') else n  # noqa: E731
    return strip(a) == strip(b)


def installed_rows(listing):
    """Rows for the installed list from `noc models list --json`: name, size text, default flag."""
    if not listing or not listing.get('ollama'):
        return []
    rows = [{'name': m['name'], 'size': fmt_bytes(m['size']), 'default': bool(m.get('is_default'))}
            for m in listing.get('models', [])]
    return sorted(rows, key=lambda r: (not r['default'], r['name']))


def suggestion_rows(presets, installed):
    """Presets not yet installed, recommended first, then by what fits best."""
    if not presets:
        return []
    order = {'gpu': 0, 'cpu': 1, 'no': 2}
    rows = [{'name': p['name'], 'note': p['note'], 'fit': FIT_TEXT.get(p['fit'], ''),
             'recommended': bool(p.get('recommended')), 'fit_key': p['fit']}
            for p in presets.get('presets', []) if not any(same_model(p['name'], i) for i in installed)]
    return sorted(rows, key=lambda r: (not r['recommended'], order.get(r['fit_key'], 3)))


_PULL_STAGES = {'pulling manifest': 'Fetching the model list', 'verifying sha256 digest': 'Verifying the download',
                'writing manifest': 'Finishing up', 'removing any unused layers': 'Cleaning up'}


class PullTracker:
    """Folds Ollama's /api/pull event stream into one overall (fraction, text).

    A pull has several layers, each with its own total, so the bar adds them up instead of
    jumping back to zero for every layer."""

    def __init__(self):
        self.layers = {}

    def feed(self, event):
        if event.get('error'):
            return None, f'Failed: {event["error"]}'
        status = event.get('status', '')
        if status == 'success':
            return 1.0, 'Done'
        if event.get('total') and status.startswith('pulling '):
            self.layers[status] = (event.get('completed', 0), event['total'])
            done = sum(c for c, _ in self.layers.values())
            total = sum(t for _, t in self.layers.values())
            return done / total, f'Downloading: {fmt_bytes(done)} of {fmt_bytes(total)}'
        return None, _PULL_STAGES.get(status, status.capitalize() or 'Working')


def iter_pull(name, base_url=None, cancelled=lambda: False, timeout=60):
    """Yield the JSON events of `POST /api/pull` for `name` until it finishes or is cancelled.

    Raises OSError when Ollama cannot be reached. Closing the connection (cancel) stops the pull."""
    request = urllib.request.Request(f'{base_url or OLLAMA_URL}/api/pull', method='POST',
                                     data=json.dumps({'model': name, 'stream': True}).encode(),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for line in response:
            if cancelled():
                return
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue


def noc_run(*args, timeout=120):
    """Run `noc <args>`; returns (ok, last line of output) so a page can show what went wrong."""
    try:
        out = subprocess.run([NOC, *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)
    text = (out.stdout + out.stderr).strip().splitlines()
    return out.returncode == 0, (text[-1] if text else '')
