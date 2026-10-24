"""iso/publish-update.sh with rclone and curl stubbed over two directory 'stores' (r2 and hetzner): bundle first, manifest
last, never overwrite, promotion keeps the bundle and serial, and the read-back verifies the signature with the same
key clients use. No network, no real bucket, no real key."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "iso/publish-update.sh"
MAKE = ROOT / "scripts/make-update.py"
HAVE_SSH_KEYGEN = shutil.which("ssh-keygen") is not None

# remote "r2:b/updates/x" -> $STORE/r2/b/updates/x ; "hz:noctraos-releases/..." -> $STORE/hz/noctraos-releases/...
RCLONE = r'''#!/usr/bin/env bash
map() { local r="${1%%:*}" rest="${1#*:}"; printf '%s/%s/%s' "$STUB_STORE" "$r" "$rest"; }
case "$1" in
  lsf) shift; while [[ "$1" == --* ]]; do shift 2; done; d="$(map "$1")"; [ -d "$d" ] || exit 0
       for f in "$d"/*; do [ -f "$f" ] && printf '%s|%s\n' "$(basename "$f")" "$(stat -c %s "$f")"; done; exit 0 ;;
  cat) f="$(map "$2")"; if [ -f "$f" ]; then cat "$f"; elif [ -n "${STUB_EMPTY_MISSING:-}" ]; then exit 0; else exit 3; fi ;;
  copyto) src="$2"; dst="$3"
       if [[ "$src" == *:* ]]; then src="$(map "$src")"; fi
       if [[ "$dst" == *:* ]]; then dst="$(map "$dst")"; fi
       [ -f "$src" ] || exit 3
       [[ "$3" == *:* ]] && echo "copyto $3" >> "$STUB_LOG"; mkdir -p "$(dirname "$dst")"; cp "$src" "$dst" ;;
esac
'''
# https://dl.noctraos.dev/updates/x -> r2 bucket b ; the hetzner host -> hz bucket noctraos-releases
CURL = r'''#!/usr/bin/env bash
out=""; url=""; args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  [ "${args[i]}" = "-o" ] && out="${args[i+1]}"
  [[ "${args[i]}" == https://* ]] && url="${args[i]}"
done
case "$url" in
  https://dl.noctraos.dev/*) f="$STUB_STORE/r2/b/${url#https://dl.noctraos.dev/}" ;;
  https://noctraos-releases.fsn1.your-objectstorage.com/*) f="$STUB_STORE/hz/noctraos-releases/${url#https://noctraos-releases.fsn1.your-objectstorage.com/}" ;;
  *) exit 6 ;;
esac
[ -f "$f" ] || exit 22
if [ -n "${STUB_PUBLIC_TAMPER:-}" ] && [[ "$f" == *manifest.json ]]; then sed 's/"notes": "/"notes": "X/' "$f" > "$out"; exit 0; fi
if [ -n "$out" ]; then
  have=$(stat -c %s "$out" 2>/dev/null || echo 0); tail -c +$((have + 1)) "$f" >> "$out"
else cat "$f"; fi
'''


@unittest.skipUnless(HAVE_SSH_KEYGEN, "ssh-keygen is needed to sign the update")
class Publish(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.store = self.tmp / "store"
        self.log = self.tmp / "log"
        self.repo = self.tmp / "repo"
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        for tool, body in (("rclone", RCLONE), ("curl", CURL)):
            (bin_dir / tool).write_text(body)
            (bin_dir / tool).chmod(0o755)
        self.key = self.tmp / "key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.key)], check=True)
        pub = (self.tmp / "key.pub").read_text().strip()
        (self.tmp / "signers").write_text(f'release@noctraos.dev namespaces="noctraos-update" {pub}\n')
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        self.commit("1")
        self.env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "STUB_STORE": str(self.store),
                    "STUB_LOG": str(self.log), "NOC_UPDATE_REPO": str(self.repo), "NOCTRAOS_UPDATE_KEY": str(self.key),
                    "UPDATE_SIGNERS": str(self.tmp / "signers"), "R2_ACCESS_KEY_ID": "x", "R2_SECRET_ACCESS_KEY": "x",
                    "R2_ENDPOINT": "x", "R2_BUCKET": "b", "AWS_ACCESS_KEY_ID": "x", "AWS_SECRET_ACCESS_KEY": "x",
                    "NOCTRAOS_S3_ENV_FILE": "/nonexistent", "VERIFY_RETRY_DELAY": "0",
                    "UPDATE_PUBLISH_LOCK": str(self.tmp / "publish.lock")}
        self.env.pop("RELEASE_STORE", None)

    def git(self, *a):
        r = subprocess.run(["git", "-C", str(self.repo), *a], capture_output=True, text=True, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)

    def commit(self, version):
        for name, text in {"VERSION": version + "\n", "install.sh": "#!/bin/sh\n", "install/lib.sh": "#\n",
                           "bin/noc": "#!/bin/sh\n"}.items():
            p = self.repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "c", "--allow-empty")

    def publish(self, *args, **env):
        return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env={**self.env, **env}, check=False)

    def manifest(self, store, channel):
        base = self.store / ("r2/b" if store == "r2" else "hz/noctraos-releases")
        return json.loads((base / f"updates/{channel}/manifest.json").read_text())

    def has_bundle(self, store, serial):
        base = self.store / ("r2/b" if store == "r2" else "hz/noctraos-releases")
        return (base / f"updates/bundles/noctraos-{serial}.tar.gz").exists()


class NightlyTests(Publish):
    def test_nightly_publishes_bundle_and_signed_manifest_to_both_stores(self):
        r = self.publish("nightly", "--ref", "HEAD", "--notes", "First.")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for store in ("r2", "hetzner"):
            self.assertTrue(self.has_bundle(store, 1), store)
            m = self.manifest(store, "nightly")
            self.assertEqual((m["serial"], m["channel"], m["rollout"]["percent"], m["notes"]), (1, "nightly", 100, "First."))
            self.assertIn(f"OK  {store}", r.stdout)
        # bundles go up before any manifest
        order = self.log.read_text().splitlines()
        first_manifest = next(i for i, l in enumerate(order) if "manifest.json" in l)
        self.assertTrue(all("bundles" in l for l in order[:first_manifest]))
        self.assertEqual(len([l for l in order[:first_manifest]]), 2)

    def test_a_store_that_answers_a_missing_manifest_with_nothing_is_a_first_publish(self):
        # The S3 stores (found on the first kubuntu publish, 2026-10-24) exit 0 with no bytes for a key that is not there.
        r = self.publish("nightly", "--flavour", "kubuntu", "--ref", "HEAD", STUB_EMPTY_MISSING="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK  r2", r.stdout)
        self.assertIn("OK  hetzner", r.stdout)

    def test_the_next_nightly_gets_the_next_serial(self):
        self.publish("nightly", "--ref", "HEAD")
        self.commit("2")
        r = self.publish("nightly", "--ref", "HEAD")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.manifest("r2", "nightly")["serial"], 2)
        self.assertEqual(self.manifest("hetzner", "nightly")["version"], "2")

    def test_a_different_bundle_already_there_stops_everything_before_any_manifest(self):
        target = self.store / "hz/noctraos-releases/updates/bundles"
        target.mkdir(parents=True)
        (target / "noctraos-1.tar.gz").write_bytes(b"someone else's bytes")
        r = self.publish("nightly", "--ref", "HEAD")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("DIFFERENT bundle", r.stderr)
        self.assertFalse((self.store / "r2/b/updates/nightly/manifest.json").exists())
        self.assertFalse((self.store / "hz/noctraos-releases/updates/nightly/manifest.json").exists())

    def test_a_publish_that_stopped_after_one_store_resumes_without_overwriting(self):
        self.publish("nightly", "--ref", "HEAD")
        shutil.rmtree(self.store / "hz")                     # one store lost everything
        r = self.publish("nightly", "--ref", "HEAD", UPDATE_STORES="hetzner")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.has_bundle("hetzner", 1))

    def test_what_the_public_host_serves_must_verify(self):
        r = self.publish("nightly", "--ref", "HEAD", STUB_PUBLIC_TAMPER="1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("does not verify", r.stderr)

    def test_a_missing_key_is_a_clear_error(self):
        r = self.publish("nightly", "--ref", "HEAD", NOCTRAOS_UPDATE_KEY=str(self.tmp / "nokey"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no signing key", r.stderr)

    def test_retry_reuses_the_newest_serial_for_each_flavour_and_repairs_a_missing_mirror(self):
        for flavour in ("zorin", "kubuntu"):
            with self.subTest(flavour=flavour):
                prefix = "" if flavour == "zorin" else "kubuntu/"
                r = self.publish("nightly", "--ref", "HEAD", "--flavour", flavour)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                target = self.store / "r2/b/updates" / prefix / "nightly/manifest.json"
                before = json.loads(target.read_text())
                bundle = self.store / "r2/b/updates" / before["bundle"]["path"]
                data = bundle.read_bytes()
                mirror_root = self.store / "hz/noctraos-releases/updates" / prefix
                (mirror_root / "nightly/manifest.json").unlink()
                (mirror_root / "bundles/noctraos-1.tar.gz").unlink()
                r = self.publish("nightly", "--ref", "HEAD", "--flavour", flavour)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                after = json.loads(target.read_text())
                self.assertEqual(after["serial"], 1)
                self.assertEqual(after["bundle"], before["bundle"])
                self.assertEqual(bundle.read_bytes(), data)
                self.assertEqual((mirror_root / "bundles/noctraos-1.tar.gz").read_bytes(), data)
                self.assertFalse((mirror_root / "bundles/noctraos-2.tar.gz").exists())

    def test_wrong_flavour_source_is_refused_before_any_upload(self):
        self.assertEqual(self.publish("nightly", "--ref", "HEAD").returncode, 0)
        for store in ("r2/b", "hz/noctraos-releases"):
            base = self.store / store / "updates"
            shutil.copytree(base / "nightly", base / "kubuntu/nightly")
        self.log.write_text("")
        r = self.publish("stable", "--rollout", "10", "--flavour", "kubuntu")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("source is for zorin, not kubuntu", r.stderr)
        self.assertEqual(self.log.read_text(), "")

    def test_retry_with_changed_bundle_construction_advances_without_replacing_old_bytes(self):
        self.assertEqual(self.publish("nightly", "--ref", "HEAD").returncode, 0)
        old = None
        for store in ("r2/b", "hz/noctraos-releases"):
            base = self.store / store / "updates"
            bundle = base / "bundles/noctraos-1.tar.gz"
            # Simulate an old builder with a different gzip timestamp but the same commit and serial.
            data = bytearray(bundle.read_bytes())
            data[4] = 1
            old = bytes(data)
            bundle.write_bytes(old)
            target = base / "nightly/manifest.json"
            manifest = json.loads(target.read_text())
            manifest["bundle"]["sha256"] = hashlib.sha256(old).hexdigest()
            target.write_text(json.dumps(manifest))
        r = self.publish("nightly", "--ref", "HEAD")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for store in ("r2/b", "hz/noctraos-releases"):
            base = self.store / store / "updates"
            self.assertEqual((base / "bundles/noctraos-1.tar.gz").read_bytes(), old)
            self.assertEqual(json.loads((base / "nightly/manifest.json").read_text())["serial"], 2)

    def test_wrong_flavour_bundle_path_is_refused_before_any_upload(self):
        self.assertEqual(self.publish("nightly", "--ref", "HEAD").returncode, 0)
        for store in ("r2/b", "hz/noctraos-releases"):
            target = self.store / store / "updates/nightly/manifest.json"
            source = json.loads(target.read_text())
            source["bundle"]["path"] = "kubuntu/bundles/noctraos-1.tar.gz"
            target.write_text(json.dumps(source))
        self.log.write_text("")
        r = self.publish("stable", "--rollout", "10")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("source bundle path does not match", r.stderr)
        self.assertEqual(self.log.read_text(), "")


class StableTests(Publish):
    def test_renewal_and_old_promote_retry_never_lower_a_flavours_rollout(self):
        for flavour in ("zorin", "kubuntu"):
            with self.subTest(flavour=flavour):
                prefix = "" if flavour == "zorin" else "kubuntu/"
                self.assertEqual(self.publish("nightly", "--ref", "HEAD", "--flavour", flavour).returncode, 0)
                self.assertEqual(self.publish("stable", "--rollout", "10", "--flavour", flavour).returncode, 0)
                saved = (self.store / "r2/b/updates" / prefix / "stable/manifest.json").read_bytes()
                self.assertEqual(self.publish("stable", "--rollout", "100", "--flavour", flavour).returncode, 0)
                # A previous partial rollout left one mirror behind. Renewal must use the widest, not the first store.
                (self.store / "r2/b/updates" / prefix / "stable/manifest.json").write_bytes(saved)
                r = self.publish("renew", "stable", "--flavour", flavour)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                for store in ("r2/b", "hz/noctraos-releases"):
                    m = json.loads((self.store / store / "updates" / prefix / "stable/manifest.json").read_text())
                    self.assertEqual((m["serial"], m["rollout"]["percent"]), (1, 100))
                r = self.publish("stable", "--rollout", "10", "--flavour", flavour)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                m = json.loads((self.store / "r2/b/updates" / prefix / "stable/manifest.json").read_text())
                self.assertEqual(m["rollout"]["percent"], 100)

    def test_an_older_nightly_cannot_replace_a_newer_stable(self):
        self.assertEqual(self.publish("nightly", "--ref", "HEAD").returncode, 0)
        saved = {store: (self.store / store / "updates/nightly/manifest.json").read_bytes()
                 for store in ("r2/b", "hz/noctraos-releases")}
        self.commit("2")
        self.assertEqual(self.publish("nightly", "--ref", "HEAD").returncode, 0)
        self.assertEqual(self.publish("stable", "--rollout", "100").returncode, 0)
        for store, data in saved.items():
            (self.store / store / "updates/nightly/manifest.json").write_bytes(data)
        self.log.write_text("")
        r = self.publish("stable", "--rollout", "10")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("stable already holds newer update 2", r.stderr)
        self.assertEqual(self.log.read_text(), "")

    def test_promotion_reuses_the_nightly_bundle_and_serial_at_a_staged_percentage(self):
        self.publish("nightly", "--ref", "HEAD")
        r = self.publish("stable", "--rollout", "10")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        n, s = self.manifest("r2", "nightly"), self.manifest("r2", "stable")
        self.assertEqual((s["serial"], s["bundle"], s["channel"], s["rollout"]["percent"]),
                         (n["serial"], n["bundle"], "stable", 10))
        self.assertEqual(self.manifest("hetzner", "stable"), s)
        # promotion uploads manifests only: the bundle was already there and is not sent again
        self.assertEqual(len([l for l in self.log.read_text().splitlines() if "bundles" in l]), 2)  # still only the nightly's two uploads

    def test_widening_and_renewing_keep_the_serial(self):
        self.publish("nightly", "--ref", "HEAD")
        self.publish("stable", "--rollout", "10")
        r = self.publish("stable", "--from", "stable", "--rollout", "100")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.manifest("r2", "stable")["rollout"]["percent"], 100)
        r = self.publish("renew", "stable")
        self.assertEqual(r.returncode, 0, r.stderr)
        m = self.manifest("r2", "stable")
        self.assertEqual((m["serial"], m["rollout"]["percent"]), (1, 100))

    def test_stable_needs_a_rollout_and_a_source(self):
        self.assertNotEqual(self.publish("stable").returncode, 0)
        r = self.publish("stable", "--rollout", "10")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nothing to publish from", r.stderr)
        self.assertNotEqual(self.publish("stable", "--rollout", "150").returncode, 0)


if __name__ == "__main__":
    unittest.main()
