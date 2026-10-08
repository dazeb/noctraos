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

# Fixes the panel can run. Anything needing root goes through the privileged helper; a fix with no
# entry here shows no button: never fall back to a bare `sudo` in a GUI.
PKEXEC = '/usr/bin/pkexec'
HELPER = '/usr/local/libexec/noctraos/noc-privileged'
FIXES = {
    'hermes:install': [HERMES, 'install'],
    # Through the allowlisted root helper: one polkit prompt, never a terminal or a bare sudo.
    'module:04d_appmanager.sh': [PKEXEC, HELPER, 'module', '04d_appmanager.sh'],
}


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


_RUN_HINT = re.compile(r'\s*\(run: [^)]*\)')


def clean_detail(detail, has_fix):
    """`noc doctor` details end with a "(run: <command>)" hint for people at a terminal; when the
    panel has a Fix button the hint is just noise."""
    return _RUN_HINT.sub('', detail or '') if has_fix else (detail or '')


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


# Ollama capability names in plain words; the ones not listed are shown as Ollama spells them.
CAPABILITY_TEXT = {'completion': 'chat', 'tools': 'tool use', 'vision': 'images', 'embedding': 'embeddings',
                   'thinking': 'reasoning', 'insert': 'code completion', 'audio': 'audio'}


def capability_text(capabilities):
    """"chat, tool use" for a model's capabilities; '' when Ollama did not report any."""
    return ', '.join(CAPABILITY_TEXT.get(c, c) for c in capabilities or [])


def installed_rows(listing):
    """Rows for the installed list from `noc models list --json`: name, size text, what it can do, default flag."""
    if not listing or not listing.get('ollama'):
        return []
    rows = [{'name': m['name'], 'size': fmt_bytes(m['size']), 'default': bool(m.get('is_default')),
             'can': capability_text(m.get('capabilities'))}
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


# ---- Updates ---------------------------------------------------------------------------------

# Steps that need root run through the helper; the rest run as the user.
PRIVILEGED_STEPS = ('apt', 'flatpak', 'noctraos')
USER_STEPS = ('mise', 'models')
STEP_ORDER = PRIVILEGED_STEPS + USER_STEPS
STEP_TITLES = {'apt': 'System packages', 'flatpak': 'Apps (Flatpak)', 'noctraos': 'NoctraOS features',
               'mise': 'Programming languages',
               'models': 'AI models'}


def _plural(n, word):
    return f'{n} {word}' if n == 1 else f'{n} {word}s'


def update_rows(updates):
    """Rows for the Updates page from `noc updates` JSON: id, title, detail, available, checked.

    Unknown counts (no network) are never shown as "up to date", and AI models start unchecked
    because refreshing them can re-download gigabytes."""
    apt = (updates.get('apt') or {})
    flatpak = (updates.get('flatpak') or {}).get('count')
    mise = (updates.get('mise') or {}).get('count')
    models = (updates.get('models') or {}).get('installed') or 0
    rows = []
    offline = updates.get('online') is False

    def row(step, detail, available, checked):
        rows.append({'id': step, 'title': STEP_TITLES[step], 'detail': detail,
                     'available': available, 'checked': checked and available})

    # Offline, a count of 0 only means "none known from the last check", never "up to date".
    nothing = 'Could not check without internet.' if offline else 'Up to date.'
    n = apt.get('count')
    if n is None:
        row('apt', 'Could not check.', False, False)
    elif n == 0:
        row('apt', nothing, False, False)
    else:
        size = apt.get('download_bytes')
        row('apt', _plural(n, 'update') + (f', {fmt_bytes(size)} to download' if size else ''), True, True)
    if flatpak is None:
        row('flatpak', 'Could not check.', False, False)
    elif flatpak == 0:
        row('flatpak', nothing, False, False)
    else:
        row('flatpak', _plural(flatpak, 'update'), True, True)
    nu = updates.get('noctraos')
    if not isinstance(nu, dict):
        row('noctraos', 'Could not check.' if offline else 'Not available on this install yet.', False, False)
    elif nu.get('status') == 'available' and nu.get('available'):
        a = nu['available']
        detail = f'NoctraOS {a.get("version", "")} (update {a.get("serial", "")})'
        if a.get('notes'):
            detail += f': {a["notes"]}'
        if a.get('relogin') or a.get('reboot'):
            detail += '. You will need to ' + ('restart' if a.get('reboot') else 'sign out and back in') + ' afterwards.'
        row('noctraos', detail, True, True)
    elif nu.get('status') in ('current', 'staged'):
        row('noctraos', 'Up to date.' if nu['status'] == 'current' else 'Up to date. A newer update is being rolled out in stages and will reach you soon.', False, False)
    else:
        row('noctraos', 'Could not check.' if nu.get('status') == 'unreachable' else 'Could not verify the update information, so nothing was changed.', False, False)
    if mise is None:
        row('mise', 'Could not check.', False, False)
    elif mise == 0:
        row('mise', nothing, False, False)
    else:
        row('mise', _plural(mise, 'tool') + ' can be updated', True, True)
    if models:
        row('models', f'Refreshes your {_plural(models, "installed model")}; downloads only what changed.', True, False)
    else:
        row('models', 'No models installed.', False, False)
    return rows


def plan_chunks(selected):
    """Split the chosen steps into the commands to run, in order: root steps through the helper
    (one prompt for all of them), then the user's own steps. Returns [(ids, argv)]."""
    chosen = [s for s in STEP_ORDER if s in selected]
    chunks = []
    root = [s for s in chosen if s in PRIVILEGED_STEPS]
    mine = [s for s in chosen if s in USER_STEPS]
    if root:
        chunks.append((root, [PKEXEC, HELPER, 'update', ','.join(root)]))
    if mine:
        chunks.append((mine, [NOC, 'update', '--json', '--only', ','.join(mine)]))
    return chunks


def exit_message(code):
    """What a non-zero exit of a chunk means to the person, '' when it is just a failed step."""
    return {126: 'The password prompt was cancelled, so nothing was changed.',
            127: 'You are not allowed to do that. Ask an administrator.'}.get(code, '')


class UpdateProgress:
    """Folds the `noc update --json` event stream (across chunks) into overall progress."""

    def __init__(self, ids):
        self.total = len(ids)
        self.finished = 0
        self.running = False
        self.failed = []
        self.text = 'Starting…'
        self.reboot_required = False

    @property
    def fraction(self):
        return self.finished / self.total if self.total else 1.0

    @property
    def display_fraction(self):
        """What the bar shows: a step in progress counts as half done, so a single long step (apt)
        does not sit at an empty bar for minutes."""
        if not self.total:
            return 1.0
        return min(1.0, (self.finished + (0.5 if self.running else 0)) / self.total)

    def feed(self, event):
        """Returns the log line to append, or None."""
        kind = event.get('event')
        if kind == 'step':
            self.running = True
            self.text = f'{event.get("label", event.get("id"))}…'
        elif kind == 'step_done':
            self.running = False
            self.finished += 1
            if not event.get('ok'):
                self.failed.append(event.get('id'))
        elif kind == 'done':
            self.reboot_required = self.reboot_required or bool(event.get('reboot_required'))
        elif kind == 'log':
            return event.get('line')
        return None


def run_events(argv):
    """Run argv and yield its output as events: JSON lines as parsed, anything else (pkexec or
    sudo messages, stderr) as {'event': 'log'}, then a final {'event': 'exit', 'code': n}."""
    try:
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    except OSError as error:
        yield {'event': 'log', 'line': str(error)}
        yield {'event': 'exit', 'code': 127}
        return
    with process:
        for line in process.stdout:
            line = line.rstrip('\n')
            if not line:
                continue
            try:
                event = json.loads(line)
                if isinstance(event, dict) and 'event' in event:
                    yield event
                    continue
            except ValueError:
                pass
            yield {'event': 'log', 'line': line}
        code = process.wait()
    yield {'event': 'exit', 'code': code}


def offline_message(updates):
    """Why the Update button is off, or '' when the network is fine."""
    if updates and not updates.get('online', True):
        return 'No internet connection. Updates need the network; local AI keeps working offline.'
    return ''


# ---- Hardware --------------------------------------------------------------------------------

GPU_BIN = '/usr/local/bin/noc-gpu'

# Rough download sizes in GB and the free space to insist on (about twice the download: unpacking
# and the apt cache). Estimates, shown as "about": the real numbers depend on the release.
GPU_NEEDS = {'nvidia': (4, 10), 'rocm': (15, 30), 'vulkan': (0.1, 2)}

_VERDICTS = {
    ('nvidia', 'modern'): 'Supported for CUDA 13.',
    ('nvidia', 'legacy'): 'Supported for CUDA 12 (an older generation).',
    ('nvidia', 'unsupported'): 'Too old for CUDA. Local models run on the CPU.',
    ('amd', 'rocm'): 'Supported by ROCm.',
    ('amd', 'override'): 'Runs ROCm with a compatibility override.',
    ('amd', 'vulkan'): 'ROCm does not support this card. Local models can use its Vulkan backend.',
}


_GPU_HINT = re.compile(r'\s*[—-]+\s*run: noc gpu install\s*$')


def gpu_json(*args, timeout=60):
    """`noc-gpu <args>` as parsed JSON, None when it is missing or fails."""
    try:
        out = subprocess.run([GPU_BIN, *args], capture_output=True, text=True, timeout=timeout)
        return json.loads(out.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def gpu_verdict(gpu):
    return _VERDICTS.get((gpu.get('vendor'), gpu.get('tier')), 'Not recognised. Local models run on the CPU.')


def install_vendors(detect):
    """Vendors with a GPU `noc-gpu install` can set up (a too-old NVIDIA card gets nothing)."""
    plan = (detect or {}).get('plan') or {}
    vendors = []
    if plan.get('nvidia') in ('modern', 'legacy'):
        vendors.append('nvidia')
    if plan.get('amd') in ('rocm', 'override', 'vulkan'):
        vendors.append('amd')
    return vendors


def _amd_kind(detect):
    return ((detect or {}).get('plan') or {}).get('amd')


def install_summary(detect):
    """What `noc-gpu install` would do, in plain words, for the consent dialog. Never automatic."""
    plan = (detect or {}).get('plan') or {}
    lines = []
    if 'nvidia' in install_vendors(detect):
        lines.append("NVIDIA: Ubuntu's signed driver and the CUDA toolkit, about "
                     f"{GPU_NEEDS['nvidia'][0]} GB to download.")
    amd = plan.get('amd')
    if amd in ('rocm', 'override'):
        lines.append(f"AMD: ROCm and the Vulkan drivers, about {GPU_NEEDS['rocm'][0]} GB to download.")
    elif amd == 'vulkan':
        lines.append('AMD: the Mesa Vulkan drivers (ROCm does not support this card), a small download.')
    if 'nvidia' in install_vendors(detect):
        lines.append('A restart is needed afterwards: the NVIDIA driver loads at the next start. '
                     'Local models keep running on the CPU until then.')
    if amd in ('rocm', 'override'):
        lines.append('You will need to log out and back in afterwards for the new GPU access to apply.')
    lines.append('This takes several minutes. Nothing changes until you press Install.')
    return lines


def disk_needed_gb(detect):
    """Free space the install should have, in GB (0 when there is nothing to install)."""
    plan = (detect or {}).get('plan') or {}
    needs = []
    if 'nvidia' in install_vendors(detect):
        needs.append(GPU_NEEDS['nvidia'][1])
    if plan.get('amd') in ('rocm', 'override'):
        needs.append(GPU_NEEDS['rocm'][1])
    elif plan.get('amd') == 'vulkan':
        needs.append(GPU_NEEDS['vulkan'][1])
    return sum(needs)


def install_blocker(detect, free_bytes):
    """Why the install must not start now, or ''."""
    need = disk_needed_gb(detect)
    if need and free_bytes is not None and free_bytes < need * 1024 ** 3:
        return f'Not enough free disk space: about {need} GB is needed, {fmt_bytes(free_bytes)} is free.'
    return ''


def hardware_state(detect, gstatus):
    """Headline and rows for the Hardware page.

    Returns {headline, level, gpus: [{name, verdict}], rows: [{status, text}], can_install, reboot}.
    `can_install` is true only when there is something to install and the stack is not ready."""
    gpus = [{'name': g.get('name', 'GPU'), 'verdict': gpu_verdict(g)} for g in (detect or {}).get('gpus', [])]
    # noc-gpu's rows end with a "run: noc gpu install" hint for people at a terminal; the page has a button.
    rows = [{**r, 'text': _GPU_HINT.sub('', r.get('text', ''))} for r in (gstatus or {}).get('rows', [])]
    reboot = bool((gstatus or {}).get('reboot_pending'))
    ready = bool((gstatus or {}).get('ready'))
    vendors = install_vendors(detect)
    if detect is None:
        headline, level = 'Could not read the GPU state', 'info'
    elif not gpus:
        headline, level = 'No GPU found. Local models run on the CPU.', 'info'
    elif reboot:
        headline, level = 'Restart to finish the GPU setup', 'warn'
    elif ready:
        headline, level = 'Your GPU is set up for local AI', 'ok'
    elif vendors:
        headline, level = 'A GPU was found but is not set up for local AI yet', 'warn'
    else:
        headline, level = 'This GPU is not usable for local AI. Models run on the CPU.', 'info'
    return {'headline': headline, 'level': level, 'gpus': gpus, 'rows': rows, 'reboot': reboot,
            'can_install': bool(vendors) and not ready and not reboot}


def gpu_install_argv(detect):
    """The privileged install command for everything this machine needs, or None."""
    vendors = install_vendors(detect)
    if not vendors:
        return None
    return [PKEXEC, HELPER, 'gpu-install', 'all' if len(vendors) > 1 else vendors[0]]


# ---- Privacy ---------------------------------------------------------------------------------

HERMES_LOCAL = [HERMES, 'local', '--no-launch']
HERMES_CLOUD = [HERMES, 'cloud']
SEARCH_SETTINGS = ['/usr/local/bin/noctraos-search', '--settings']
WEATHER_SETUP = ['/usr/local/bin/noctraos-weather', '--setup']


def hermes_mode():
    """cloud | local | other, or None when Hermes is not installed."""
    try:
        out = subprocess.run([HERMES, 'mode'], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out if out in ('cloud', 'local', 'other') else None


def hermes_privacy(mode):
    """What the Privacy page says about Hermes for each mode. The free tier is never called local."""
    if mode is None:
        return {'headline': 'Hermes is not installed yet', 'level': 'info', 'can_switch': False,
                'text': 'Hermes Desktop is set up on first boot. Come back when it is ready.'}
    if mode == 'other':
        return {'headline': 'Hermes uses your own provider', 'level': 'info', 'can_switch': False,
                'text': 'You set a provider in Hermes itself, so this panel leaves it alone.'}
    if mode == 'local':
        return {'headline': 'Local only', 'level': 'ok', 'can_switch': True,
                'text': 'Hermes talks to the model on this computer. Nothing you type to it leaves this computer.'}
    return {'headline': 'Nous free tier (cloud)', 'level': 'warn', 'can_switch': True,
            'text': "Hermes uses Nous Research's free cloud service, so what you type to it leaves this "
                    'computer. Switch to local only to keep it here.'}


def switch_command(target, current):
    """argv to move Hermes to `target` ('local' or 'cloud'), None when it is already there, the
    user runs their own provider, or the target is not a known mode."""
    if current in (None, 'other') or target == current:
        return None
    return {'local': HERMES_LOCAL, 'cloud': HERMES_CLOUD}.get(target)


def run_ok(argv, timeout=120):
    """Run argv; returns (ok, last line of its output) so a page can say what went wrong."""
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)
    text = (out.stdout + out.stderr).strip().splitlines()
    return out.returncode == 0, (text[-1] if text else '')
