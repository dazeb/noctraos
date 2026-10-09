#!/usr/bin/env python3
"""make-update.py — build and sign a NoctraOS update (the release side of bin/noc-selfupdate).

  make-update.py bundle   --ref REF --serial N --out DIR        git ref -> DIR/bundles/noctraos-N.tar.gz + DIR/bundle.json
  make-update.py manifest --bundle-json F|--from-manifest F --channel C --rollout PCT --key KEY --out DIR [...]
                                                                -> DIR/C/manifest.json and manifest.json.sig
  make-update.py serial   [MANIFEST ...]                        next serial: highest in the given manifests, plus one

A bundle is the file set that install/07_persistence.sh keeps as the root-owned snapshot, plus migrations/ and
.update.json. It is built from a git ref with fixed timestamps and owners, so the same commit gives the same bytes.
The manifest names the bundle by SHA-256 and is signed with `ssh-keygen -Y sign` (ed25519, namespace noctraos-update);
clients verify it against /usr/local/share/noctraos/update-signers. Promoting a nightly update to stable is
`manifest --from-manifest nightly/manifest.json --channel stable --rollout 10`: same bundle, same serial.
Design: docs/updates.md.
"""
import argparse
import datetime
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile

ROOT = os.environ.get('NOC_UPDATE_REPO') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # NOC_UPDATE_REPO: tests
NAMESPACE = 'noctraos-update'
FORMAT = 1
TIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
META = '.update.json'
# Keep equal to BUNDLE_ITEMS in bin/noc-selfupdate and the item list in install/07_persistence.sh (a test pins all three).
ITEMS = ['VERSION', 'install.sh', 'install', 'bin', 'configs', 'scripts', 'assets', 'help', 'extensions', 'branding',
         'search', 'control', 'migrations']
EXCLUDE_PREFIXES = ('assets/promo/', 'assets/social/')   # module 07 removes them from the snapshot too


def git(*args, check=True):
    r = subprocess.run(['git', '-C', ROOT, *args], capture_output=True)
    if check and r.returncode != 0:
        sys.exit(f'git {" ".join(args)}: {r.stderr.decode().strip()}')
    return r.stdout


def build_bundle(ref, serial, out):
    commit = git('rev-parse', '--verify', f'{ref}^{{commit}}').decode().strip()
    version = git('show', f'{commit}:VERSION').decode().strip()
    present = [i for i in ITEMS
               if subprocess.run(['git', '-C', ROOT, 'cat-file', '-e', f'{commit}:{i}'], capture_output=True).returncode == 0]
    for needed in ('VERSION', 'install.sh', 'install', 'bin'):
        if needed not in present:
            sys.exit(f'{ref} has no {needed}: not a NoctraOS tree')
    raw = git('archive', '--format=tar', commit, '--', *present)
    meta = json.dumps({'serial': serial, 'version': version, 'commit': commit}, sort_keys=True, indent=1) + '\n'
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=tarfile.PAX_FORMAT) as dst, \
            tarfile.open(fileobj=io.BytesIO(raw)) as src:
        members = sorted(src.getmembers(), key=lambda m: m.name)
        for m in members:
            if m.name.startswith(EXCLUDE_PREFIXES) or m.name in ('assets/promo', 'assets/social'):
                continue
            if not (m.isfile() or m.isdir()):
                sys.exit(f'{m.name} is a {"symlink" if m.issym() else "special file"}: bundles hold plain files only')
            m.uid = m.gid = 0
            m.uname = m.gname = ''
            m.mtime = 0
            m.mode = (0o755 if (m.isdir() or m.mode & 0o111) else 0o644)
            m.pax_headers = {}
            dst.addfile(m, src.extractfile(m) if m.isfile() else None)
        info = tarfile.TarInfo(META)
        info.size, info.mtime, info.mode = len(meta.encode()), 0, 0o644
        dst.addfile(info, io.BytesIO(meta.encode()))
    gz = io.BytesIO()
    with gzip.GzipFile(fileobj=gz, mode='wb', mtime=0, compresslevel=9) as g:
        g.write(buf.getvalue())
    data = gz.getvalue()
    os.makedirs(os.path.join(out, 'bundles'), exist_ok=True)
    name = f'bundles/noctraos-{serial}.tar.gz'
    with open(os.path.join(out, name), 'wb') as f:
        f.write(data)
    info = {'serial': serial, 'version': version, 'commit': commit, 'path': name,
            'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
    with open(os.path.join(out, 'bundle.json'), 'w') as f:
        json.dump(info, f, indent=1, sort_keys=True)
        f.write('\n')
    return info


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)


def sign(path, key):
    sig = path + '.sig'
    if os.path.exists(sig):
        os.unlink(sig)
    r = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', NAMESPACE, path], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(sig):
        sys.exit(f'ssh-keygen -Y sign failed: {r.stderr.strip()}')


def build_manifest(args):
    if bool(args.bundle_json) == bool(args.from_manifest):
        sys.exit('give exactly one of --bundle-json and --from-manifest')
    src = json.load(open(args.bundle_json or args.from_manifest))
    if args.from_manifest:
        bundle = dict(src['bundle'])
        serial, version, commit = src['serial'], src['version'], src.get('commit', '')
        notes = args.notes if args.notes is not None else src.get('notes', '')
        relogin = args.relogin or bool(src.get('relogin'))
        reboot = args.reboot or bool(src.get('reboot'))
    else:
        bundle = {k: src[k] for k in ('path', 'sha256', 'size')}
        serial, version, commit = src['serial'], src['version'], src['commit']
        notes, relogin, reboot = args.notes or '', args.relogin, args.reboot
    if not 0 <= args.rollout <= 100:
        sys.exit('--rollout is a percentage, 0 to 100')
    issued = now()
    manifest = {'format': FORMAT, 'channel': args.channel, 'serial': serial, 'version': version, 'commit': commit,
                'issued': issued.strftime(TIME_FORMAT),
                'expires': (issued + datetime.timedelta(days=args.expires_days)).strftime(TIME_FORMAT),
                'rollout': {'percent': args.rollout}, 'bundle': bundle, 'notes': notes,
                'relogin': relogin, 'reboot': reboot}
    outdir = os.path.join(args.out, args.channel)
    os.makedirs(outdir, exist_ok=True)
    target = os.path.join(outdir, 'manifest.json')
    with open(target, 'w') as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write('\n')
    sign(target, args.key)
    return target


def next_serial(paths):
    best = 0
    for p in paths:
        try:
            best = max(best, int(json.load(open(p))['serial']))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return best + 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('bundle')
    b.add_argument('--ref', required=True)
    b.add_argument('--serial', type=int, required=True)
    b.add_argument('--out', required=True)
    m = sub.add_parser('manifest')
    m.add_argument('--bundle-json')
    m.add_argument('--from-manifest')
    m.add_argument('--channel', choices=('stable', 'nightly'), required=True)
    m.add_argument('--rollout', type=int, default=100)
    m.add_argument('--expires-days', type=int, default=30)
    m.add_argument('--notes')
    m.add_argument('--relogin', action='store_true')
    m.add_argument('--reboot', action='store_true')
    m.add_argument('--key', required=True)
    m.add_argument('--out', required=True)
    s = sub.add_parser('serial')
    s.add_argument('manifests', nargs='*')
    sub.add_parser('items', help='print the top-level paths a bundle carries, one per line')
    args = p.parse_args(argv)
    if args.cmd == 'bundle':
        if args.serial < 1:
            sys.exit('--serial starts at 1')
        info = build_bundle(args.ref, args.serial, args.out)
        print(json.dumps(info))
    elif args.cmd == 'manifest':
        print(build_manifest(args))
    elif args.cmd == 'items':
        print('\n'.join(ITEMS))
    else:
        print(next_serial(args.manifests))
    return 0


if __name__ == '__main__':
    sys.exit(main())
