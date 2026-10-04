"""User-owned search index. No shell execution, network calls, or elevated reads."""
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import time

VIRTUAL = ('/proc', '/sys', '/dev', '/run')
TEXT_LIMIT = 128 * 1024


def cache_dir():
    directory = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'noctraos-search'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    return directory


def index_options(settings):
    return {key: settings[key] for key in ('roots', 'hidden', 'contents')}


def walk_files(roots, hidden):
    """Do not follow directory symlinks or read virtual filesystems."""
    seen = set()
    for root in roots:
        root = Path(root).expanduser().resolve()
        if not root.is_dir() or any(root == Path(v) or Path(v) in root.parents for v in VIRTUAL):
            continue
        stack = [root]
        while stack:
            directory = stack.pop()
            if directory in seen:
                continue
            seen.add(directory)
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        path = Path(entry.path)
                        if str(path) in VIRTUAL or (not hidden and entry.name.startswith('.')):
                            continue
                        try:
                            is_dir = entry.is_dir(follow_symlinks=False)
                            if is_dir:
                                stack.append(path)
                            # Exclude sockets/devices/pipes, including symlinks to them.
                            if not (path.is_dir() or path.is_file()) or not os.access(path, os.R_OK):
                                continue
                            yield path, is_dir
                        except OSError:
                            continue
            except OSError:
                continue


def text_content(path):
    """Never block on FIFOs or follow a link into a protected/virtual tree."""
    try:
        real = path.resolve()
        if any(real == Path(v) or Path(v) in real.parents for v in VIRTUAL):
            return ''
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as source:
            metadata = os.fstat(source.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > TEXT_LIMIT:
                return ''
            data = source.read(TEXT_LIMIT + 1)
        if b'\0' in data or len(data) > TEXT_LIMIT:
            return ''
        return data.decode('utf-8')
    except (OSError, UnicodeError):
        return ''


def build_index(directory, settings):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    with (directory / 'index.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        temporary = directory / 'index.building'
        temporary.unlink(missing_ok=True)
        connection = sqlite3.connect(temporary)
        temporary.chmod(0o600)
        try:
            connection.executescript('''
                PRAGMA journal_mode=OFF;
                CREATE TABLE files(path TEXT PRIMARY KEY, name TEXT, directory INTEGER);
                CREATE VIRTUAL TABLE names USING fts5(name, tokenize='trigram');
                CREATE VIRTUAL TABLE contents USING fts5(text);
                CREATE TABLE metadata(value TEXT);
            ''')
            for path, is_dir in walk_files(settings['roots'], settings['hidden']):
                cursor = connection.execute('INSERT OR IGNORE INTO files VALUES(?,?,?)',
                                            (str(path), path.name, int(is_dir)))
                if cursor.rowcount == 0:
                    continue
                row = cursor.lastrowid
                connection.execute('INSERT INTO names(rowid,name) VALUES(?,?)',
                                   (row, path.name.casefold()))
                if settings['contents'] and not is_dir:
                    text = text_content(path)
                    if text:
                        connection.execute('INSERT INTO contents(rowid,text) VALUES(?,?)', (row, text))
            connection.execute('INSERT INTO metadata VALUES(?)',
                               (json.dumps({'options': index_options(settings), 'updated': time.time()}),))
            connection.commit()
        finally:
            connection.close()
        # Readers retain the previous complete index throughout the rebuild.
        temporary.replace(directory / 'index.sqlite')
        return True


def index_state(directory, settings):
    try:
        with closing(sqlite3.connect((Path(directory) / 'index.sqlite').resolve().as_uri() + '?mode=ro', uri=True)) as db:
            metadata = json.loads(db.execute('SELECT value FROM metadata').fetchone()[0])
        return metadata['options'] == index_options(settings), metadata['updated']
    except (sqlite3.Error, OSError, ValueError, TypeError):
        return False, 0


def search_files(directory, query, settings, limit):
    if not settings['files']:
        return [], ''
    if len(query.strip()) < 3:
        return [], 'Type at least 3 characters to search files.'
    current, _ = index_state(directory, settings)
    # Never expose results from a scope or privacy setting that has been removed.
    if not current:
        return [], 'File index is updating. Apps and web search are ready.'
    term = query.strip().casefold()
    phrase = '"' + term.replace('"', '""') + '"'
    results = []
    try:
        with closing(sqlite3.connect((Path(directory) / 'index.sqlite').resolve().as_uri() + '?mode=ro', uri=True)) as db:
            home = str(Path.home()) + '/'
            ranking = ' ORDER BY CASE WHEN substr(path,1,?)=? THEN 0 ELSE 1 END, files.name=? COLLATE NOCASE DESC, length(files.name), path LIMIT ?'
            rank_args = (len(home), home, term, limit * 4)
            if '/' in term:
                escaped = term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
                rows = db.execute("SELECT path,name,directory FROM files WHERE lower(path) LIKE ? ESCAPE '\\'" + ranking,
                                  ('%' + escaped + '%', *rank_args)).fetchall()
            else:
                rows = db.execute('''SELECT path,files.name,directory FROM names
                    JOIN files ON files.rowid=names.rowid WHERE names MATCH ?''' + ranking,
                                  (phrase, *rank_args)).fetchall()
            rows.sort(key=lambda row: (not Path(row[0]).is_relative_to(Path.home()),
                                       row[1].casefold() != term, len(row[1]), row[0]))
            for path, name, is_dir in rows:
                # Refresh access checks: stale entries must not reveal inaccessible paths.
                if not os.access(path, os.R_OK) or not os.path.exists(path):
                    continue
                results.append({'kind': 'file', 'title': name, 'detail': path, 'path': path,
                                'icon': 'folder-symbolic' if is_dir else 'text-x-generic-symbolic'})
                if len(results) >= limit:
                    break
            if settings['contents'] and len(results) < limit:
                words = ['"' + word.replace('"', '""') + '"' for word in term.split()]
                rows = db.execute('''SELECT path,name,snippet(contents,0,'','', ' … ',16)
                    FROM contents JOIN files ON files.rowid=contents.rowid
                    WHERE contents MATCH ? LIMIT ?''', (' AND '.join(words), limit)).fetchall()
                seen = {r['path'] for r in results}
                for path, name, snippet in rows:
                    if path in seen or not os.access(path, os.R_OK) or not os.path.exists(path):
                        continue
                    results.append({'kind': 'file', 'title': name, 'detail': f'{path} — {snippet}',
                                    'path': path, 'icon': 'text-x-generic-symbolic'})
                    if len(results) >= limit:
                        break
    except sqlite3.Error:
        return [], 'File index is unavailable. Rebuild it in Search settings.'
    return results, ''


def search_clipboard(query, limit):
    # One fixed script reads all text history; query text is never evaluated as code.
    script = """var config=JSON.parse(str(input())); var found=[]; var seen=Object.create(null);
        var query=config.query.toLowerCase(); var names=tab();
        for(var t=0;t<names.length && found.length<config.limit;t++) {
            tab(names[t]);
            for(var i=0;i<size() && found.length<config.limit;i++) {
                var text=str(read('text/plain',i));
                if(text && text.toLowerCase().indexOf(query)>=0 && !seen[text]) {
                    seen[text]=true; found.push({text:text,tab:names[t]});
                }
            }
        } print(JSON.stringify(found));"""
    try:
        process = subprocess.run(['copyq', 'eval', script], capture_output=True, text=True,
                                 input=json.dumps({'query': query, 'limit': limit}),
                                 # If this starts the server, it must be the X11 one (see copyq.desktop).
                                 env={**os.environ, 'QT_QPA_PLATFORM': 'xcb'},
                                 timeout=3, check=True)
        items = json.loads(process.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return [], 'Clipboard history is unavailable. Start CopyQ to search it.'
    matches = []
    seen = set()
    for item in items:
        text = item['text']
        if query.casefold() not in text.casefold() or text in seen:
            continue
        seen.add(text)
        matches.append({'kind': 'clipboard', 'title': ' '.join(text.split())[:160],
                        'detail': 'Clipboard · Enter to copy', 'text': text,
                        'icon': 'edit-paste-symbolic'})
        if len(matches) >= limit:
            break
    return matches, ''
