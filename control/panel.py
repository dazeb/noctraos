"""Control Panel logic that needs no GTK: turn `noc` JSON into what the window shows.

The panel is a GUI for `noc`, not a second implementation (docs/control-panel-plan.md): every
number on screen comes from `noc status --json` and friends, so this module only formats it.
Kept free of PyGObject so the unit tests (and CI) can import it.
"""
import datetime
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


def _apps_card(apps):
    """Hermes, Ollama, AppManager and the coding agents: how far behind their newest upstream release."""
    rows = (apps or {}).get('apps') if isinstance(apps, dict) else None
    if not rows or all(r.get('status') == 'unknown' for r in rows if r.get('installed')):
        return Card('apps', 'Apps', 'Not checked yet', 'Open Apps to check Hermes, Ollama and the coding agents.', 'info', 'apps')
    behind = [r for r in rows if r.get('status') == 'outdated']
    if behind:
        names = ', '.join(f'{r["title"]} {r["installed"]} → {r["latest"]}' for r in behind[:2]) + ('…' if len(behind) > 2 else '')
        return Card('apps', 'Apps', f'{len(behind)} update{"" if len(behind) == 1 else "s"} available', names, 'warn', 'apps')
    hermes = next((r for r in rows if r.get('id') == 'hermes' and r.get('installed')), None)
    return Card('apps', 'Apps', 'Up to date', f'Hermes {hermes["installed"]}' if hermes else '', 'ok', 'apps')


def _accounts_card(accounts, skipped=None):
    """Git needs a name and e-mail before the first commit, and GitHub a sign-in before the first push: both stop a
    newcomer cold with a cryptic message, so the Overview says plainly when they are not done yet. A chore the person
    chose to do themselves is not nagged about."""
    state = accounts_state(accounts, skipped)
    if state is None:
        return Card('accounts', 'Accounts', 'Not checked yet', 'Git name and e-mail, GitHub sign-in.', 'info', 'accounts')
    if state['done']:
        return Card('accounts', 'Accounts', 'Ready', f'{state["git_text"]}. {state["github_text"]}.', 'ok', 'accounts')
    if state['todo']:
        return Card('accounts', 'Accounts', 'Needs setting up',
                    ' and '.join(SKIPPABLE[t] for t in state['todo']) + ' (one minute, no terminal).', 'warn', 'accounts')
    return Card('accounts', 'Accounts', 'You are doing this yourself',
                'Skipped: ' + ' and '.join(SKIPPABLE[t] for t in state['skipped']) + '. Open Accounts to change that.',
                'info', 'accounts')


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
        _accounts_card(status.get('accounts'), status.get('skipped')),
        _apps_card(status.get('apps')),
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


# ---- Doing it yourself: skipped chores and terminal tips ---------------------------------------
#
# The panel is mouse first and the terminal a close second (docs/objectives.md). Two things follow: every setup chore
# can be declined ("No, I'll set it up myself", remembered by `noc skip`), and every action has a small "Terminal" tip
# that names the commands for it. The commands stay out of sight until the person hovers or clicks.

SKIPPABLE = {'git': 'Git name and e-mail', 'github': 'GitHub sign-in', 'gpu': 'GPU setup for local AI'}

# What each action is in a terminal, by the id the page uses. Plain tools (git, gh) come first where a person who knows a
# terminal would reach for them; the `noc` form is the one the panel itself runs. tests/test_control_core.py checks that
# every command here exists, so a renamed verb cannot leave a stale tip behind.
TERMINAL = {
    'git': ['git config --global user.name "Your Name"', 'git config --global user.email you@example.com'],
    'github': ['gh auth login --web', 'gh auth setup-git'],
    'gpu': ['noc gpu status', 'noc gpu install'],
    'updates': ['noc update', 'noc update --only mise,models'],
    'apps': ['noc apps', 'noc-upstream update --only <app>'],
    'models': ['noc models list', 'noc models pull <model>', 'noc models default <model>', 'noc models rm <model>'],
    'privacy': ['noctraos-hermes local', 'noctraos-hermes cloud', 'noctraos-search --settings', 'noctraos-weather --setup'],
    'health': ['noc doctor'],
}


def terminal_commands(key):
    """The terminal commands for an action, one per line, as text to copy; '' for an unknown key."""
    return '\n'.join(TERMINAL.get(key, []))


def terminal_tip(key):
    """The tooltip of a page's Terminal button."""
    commands = TERMINAL.get(key)
    if not commands:
        return ''
    return 'In a terminal:\n' + '\n'.join(f'  {c}' for c in commands) + '\n\nClick to copy.'


def skipped_set(skipped):
    """The chores in a `noc skip list --json` answer (or a `noc status` document's `skipped`), unknown ids dropped."""
    return {s for s in skipped if s in SKIPPABLE} if isinstance(skipped, list) else set()


def skip_command(chore, skip=True):
    """argv that records (or, with skip=False, takes back) the choice to do a chore yourself; None for an unknown chore."""
    return [NOC, 'skip', 'add' if skip else 'rm', chore] if chore in SKIPPABLE else None


def skipped_text(chore):
    """Shown in place of a chore the person skipped: what they chose, and the terminal route they now own."""
    return ('You chose to set this up yourself. In a terminal:\n' +
            '\n'.join(f'  {c}' for c in TERMINAL.get(chore, [])) + '\n\nChange your mind any time with the button below.')


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
USER_STEPS = ('mise', 'apps', 'models')
STEP_ORDER = PRIVILEGED_STEPS + USER_STEPS
STEP_TITLES = {'apt': 'System packages', 'flatpak': 'Apps (Flatpak)', 'noctraos': 'NoctraOS features',
               'mise': 'Programming languages', 'apps': 'Hermes and coding agents',
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
    ap = updates.get('apps')
    behind = [r for r in (ap or {}).get('apps', []) if r.get('status') == 'outdated' and r.get('updater') == 'user']
    if not isinstance(ap, dict):
        row('apps', 'Could not check.' if offline else 'Not available on this install yet.', False, False)
    elif behind:
        names = ', '.join(f'{r["title"]} {r["installed"]} → {r["latest"]}' for r in behind[:4])
        row('apps', names + ('…' if len(behind) > 4 else ''), True, True)
    elif ap.get('online') is False:
        row('apps', 'Could not check for new releases.', False, False)
    else:
        row('apps', 'Up to date with the newest releases.', False, False)
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


# ---- Accounts (Git identity, GitHub sign-in) --------------------------------------------------

ACCOUNTS = '/usr/local/bin/noc-accounts'
ACCOUNTS_LOGIN = [ACCOUNTS, 'github', 'login', '--json']
_EMAIL = re.compile(r'^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$')


def accounts_state(accounts, skipped=None):
    """What the Accounts page and card say, from `noc accounts status --json` (and the `noc skip` list); None when it did
    not answer. `done` means both chores are really done; `todo` are the ones still asking, `skipped` the ones the person
    chose to do themselves (a chore that is already done is never "skipped")."""
    if not isinstance(accounts, dict) or 'git' not in accounts:
        return None
    git, hub = accounts.get('git') or {}, accounts.get('github') or {}
    git_ready = bool(git.get('name') and git.get('email'))
    signed = bool(hub.get('signed_in'))
    chosen = skipped_set(skipped)
    todo = [t for t, ok in (('git', git_ready), ('github', signed)) if not ok and t not in chosen]
    passed = [t for t, ok in (('git', git_ready), ('github', signed)) if not ok and t in chosen]
    return {'git_ready': git_ready, 'signed_in': signed, 'done': git_ready and signed, 'todo': todo, 'skipped': passed,
            'git_skipped': 'git' in passed, 'github_skipped': 'github' in passed,
            'name': git.get('name') or '', 'email': git.get('email') or '', 'login': hub.get('login') or '',
            'gh_installed': bool(hub.get('installed')),
            'git_text': f'Git signs your work as {git["name"]}' if git_ready else 'Git does not know your name yet',
            'github_text': (f'Signed in to GitHub as {hub["login"]}' if hub.get('login') else 'Signed in to GitHub')
            if signed else ('Not signed in to GitHub' if hub.get('installed') else 'GitHub\'s tool is not installed')}


def identity_problem(name, email):
    """Why the name/e-mail cannot be saved, in words for a newcomer, or ''. The saving command checks again."""
    name, email = (name or '').strip(), (email or '').strip()
    if not name:
        return 'Type your name.'
    if len(name) > 100 or re.search(r'[\x00-\x1f<>]', name):
        return 'That name has characters Git cannot use.'
    if not _EMAIL.match(email):
        return 'That does not look like an e-mail address.'
    return ''


def suggested_identity(suggestion, private=True):
    """(name, e-mail) to fill in from `noc accounts github suggest --json`. GitHub's private address is the default: it
    works even when the person hides their e-mail, and GitHub refuses pushes that would reveal a private one."""
    if not isinstance(suggestion, dict) or not suggestion.get('login'):
        return None
    email = suggestion.get('private_email') if private or not suggestion.get('public_email') else suggestion['public_email']
    return suggestion.get('name') or suggestion['login'], email


def parse_event(line):
    """One line of `noc accounts github login --json` as an event dict, or None for anything else."""
    try:
        event = json.loads(line)
    except ValueError:
        return None
    return event if isinstance(event, dict) and 'event' in event else None


# ---- Apps (upstream releases) ----------------------------------------------------------------

UPSTREAM = '/usr/local/bin/noc-upstream'


def _ago(stamp):
    try:
        then = datetime.datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return ''
    return fmt_age(max(0, (datetime.datetime.now(datetime.timezone.utc) - then).total_seconds()))


def app_action(row):
    """How to update one app: (argv, confirmation text or ''), or None when there is nothing to do.
    User-level apps (Hermes, the coding agents) update as the person; root ones go through the privileged helper."""
    if row.get('status') != 'outdated':
        return None
    if row.get('updater') == 'user':
        return [UPSTREAM, 'update', '--only', row['id']], ''
    if row.get('updater') == 'root' and row.get('module'):
        text = f'Update {row["title"]} from {row["installed"]} to {row["latest"]}?'
        if row['id'] == 'ollama':
            text += ' This downloads about 1.4 GB and restarts the local AI service, so a model that is running stops.'
        return [PKEXEC, HELPER, 'module', row['module']], text
    return None


def apps_rows(data):
    """Rows for the Apps page from `noc apps --json`: critical apps first, then the rest, coding agents last."""
    rows = []
    for r in (data or {}).get('apps', []):
        inst, late, status = r.get('installed'), r.get('latest'), r.get('status')
        if status == 'outdated':
            text, level = f'Update available: {inst} → {late}', 'warn'
        elif status == 'current':
            text, level = 'Up to date', 'ok'
        elif status == 'absent':
            text, level = ('Not installed yet. It installs the first time you open it.' if r.get('agent')
                           else 'Not installed.'), 'info'
        else:
            text, level = 'Could not check for a newer release.', 'info'
        notes = []
        if inst:
            notes.append(f'Version {inst}')
        if late and status != 'outdated':
            notes.append(f'newest release {late}')
        if r.get('updated_at'):
            notes.append(f'changed {_ago(r["updated_at"])}')
        if r.get('stale'):
            notes.append('release information is from an earlier check')
        action = app_action(r)
        rows.append({'id': r['id'], 'title': r['title'], 'critical': bool(r.get('critical')), 'agent': bool(r.get('agent')),
                     'about': r.get('about', ''), 'status': text, 'level': level, 'detail': ', '.join(notes),
                     'url': r.get('url', ''), 'argv': action[0] if action else None,
                     'confirm': action[1] if action else '', 'updater': r.get('updater')})
    rows.sort(key=lambda x: (not x['critical'], x['agent'], x['title'].lower()))
    return rows


def apps_headline(data):
    if not isinstance(data, dict) or not data.get('apps'):
        return 'Could not read the app versions.'
    n = data.get('updates', 0)
    when = f' Last checked {_ago(data["checked_at"])}.' if data.get('checked_at') else ''
    if not data.get('online', True):
        return 'No internet connection, so newer releases could not be looked up.' + when
    return (f'{n} update{"" if n == 1 else "s"} available.' if n else 'Everything is on its newest release.') + when


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


def hardware_state(detect, gstatus, skipped=None):
    """Headline and rows for the Hardware page.

    Returns {headline, level, gpus: [{name, verdict}], rows: [{status, text}], can_install, skipped, reboot}.
    `can_install` is true only when there is something to install, the stack is not ready and the person has not chosen
    to set the GPU up themselves (`skipped`; then the page offers to take that back instead)."""
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
    elif vendors and 'gpu' in skipped_set(skipped):
        headline, level = 'A GPU was found. You chose to set it up yourself.', 'info'
    elif vendors:
        headline, level = 'A GPU was found but is not set up for local AI yet', 'warn'
    else:
        headline, level = 'This GPU is not usable for local AI. Models run on the CPU.', 'info'
    offer = bool(vendors) and not ready and not reboot
    chosen = offer and 'gpu' in skipped_set(skipped)
    return {'headline': headline, 'level': level, 'gpus': gpus, 'rows': rows, 'reboot': reboot,
            'can_install': offer and not chosen, 'skipped': chosen}


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
