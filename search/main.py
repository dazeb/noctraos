#!/usr/bin/python3
"""CLI bridge between GNOME Shell and the user-owned index/settings."""
import argparse
import json
import subprocess
import sys
import time

import browsers
from core import build_index, cache_dir, index_state, search_clipboard, search_files

SCHEMA = 'org.gnome.shell.extensions.noctraos-search'


def get_settings():
    from gi.repository import Gio
    return Gio.Settings.new(SCHEMA)


def options(settings):
    return {key: settings.get_value(key).unpack() for key in
            ('apps', 'files', 'clipboard', 'web', 'roots', 'hidden', 'contents', 'max-results',
             'history', 'history-browsers')}


def request_index(restart=True):
    subprocess.run(['systemctl', '--user', 'restart' if restart else 'start', '--no-block', 'noctraos-search-index.service'],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def setup_user():
    """Once per account: preserve extensions and all later user choices."""
    from pathlib import Path
    from gi.repository import Gio
    marker = Path.home() / '.config/noctraos/search-provisioned'
    if marker.exists():
        return
    uuid = 'noctraos-search@noctraos.local'
    shell = Gio.Settings.new('org.gnome.shell')
    enabled = shell.get_strv('enabled-extensions')
    if uuid not in enabled and not shell.set_strv('enabled-extensions', enabled + [uuid]):
        raise RuntimeError('Extension settings are locked')
    wm = Gio.Settings.new('org.gnome.desktop.wm.keybindings')
    forward = wm.get_strv('switch-input-source')
    occupied = [key for key in forward if key.lower() in ('<super>space', '<mod4>space')]
    if occupied:
        forward = [key for key in forward if key not in occupied]
        if '<Shift><Super>space' not in forward:
            forward.append('<Shift><Super>space')
        if not wm.set_strv('switch-input-source', forward):
            raise RuntimeError('Input-source shortcut is locked')
        backward = [key for key in wm.get_strv('switch-input-source-backward')
                    if key.lower() not in ('<shift><super>space', '<super><shift>space')]
        if '<Control><Shift><Super>space' not in backward:
            backward.append('<Control><Shift><Super>space')
        if not wm.set_strv('switch-input-source-backward', backward):
            raise RuntimeError('Input-source shortcut is locked')
    Gio.Settings.sync()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument('--query')
    commands.add_argument('--index', action='store_true')
    commands.add_argument('--ensure-index', action='store_true')
    commands.add_argument('--settings', action='store_true')
    commands.add_argument('--setup', action='store_true')
    commands.add_argument('--status', action='store_true')
    commands.add_argument('--setup-history', action='store_true')
    args = parser.parse_args()
    settings = get_settings()
    config = options(settings)
    if args.setup:
        setup_user()
        return
    if args.settings:
        from preferences import show_settings
        show_settings(settings)
        return
    if args.setup_history:
        from preferences import show_history_setup
        show_history_setup(settings)
        return
    if args.status:
        setup = settings.get_string('history-setup')
        found = browsers.detected()
        default = browsers.default_browser()
        print(json.dumps({'history': {
            'setup': setup, 'enabled': config['history'],
            'browsers': [dict(b, default=b['id'] == default) for b in found],
            # Only ask once there is something to search.
            'prompt': setup == 'unset' and bool(found)}}))
        return
    directory = cache_dir()
    if args.index or args.ensure_index:
        if config['history']:
            browsers.refresh_history(directory, config['history-browsers'])
        else:
            browsers.clear_history(directory)
        if config['files']:
            current, updated = index_state(directory, config)
            if args.index or not current or time.time() - updated > 900:
                build_index(directory, config)
        else:
            (directory / 'index.sqlite').unlink(missing_ok=True)
            (directory / 'index.building').unlink(missing_ok=True)
        return
    query = args.query.strip()[:512]
    results, notices = [], []
    if query:
        files, notice = search_files(directory, query, config, config['max-results'])
        results.extend(files)
        if notice:
            notices.append(notice)
        if config['files'] and not index_state(directory, config)[0]:
            request_index(restart=False)
        if config['history']:
            browsers.refresh_history(directory, config['history-browsers'], max_age=120)
            pages, notice = browsers.search_history(directory, query, config['history-browsers'],
                                                    config['max-results'])
            results.extend(pages)
            if notice:
                notices.append(notice)
        if config['clipboard']:
            clips, notice = search_clipboard(query, config['max-results'])
            results.extend(clips)
            if notice:
                notices.append(notice)
    print(json.dumps({'results': results, 'notice': ' '.join(notices)}, ensure_ascii=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Noctra Search: {error}', file=sys.stderr)
        sys.exit(1)
