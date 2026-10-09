# AGENTS.md — noctraos

Instructions for coding agents working in this repository. Read fully before
changing anything; the pitfalls section saves real debugging time.

## What this repo is

NoctraOS (`noctraos`) is an **AI development workstation OS**, on an Ubuntu base (Zorin OS 18.x today) — Omarchy's idea without
the tiling-WM learning curve. It is delivered as a bootable **ISO**; the
Omakub-style provisioner (`install.sh`) is the engine baked into it. Contents:
local Ollama stack, a six-agent start menu, mise-managed runtimes, a dark +
amber theme, and the **Super+Space** system search as the headline feature.

Read `docs/objectives.md` first: it defines the audience, principles
(muscle memory over Windows imitation, no terminal required, no tiling WM),
the onboarding goal, and non-goals. Keep it current when direction changes.

The repo is **public on GitHub** (`github.com/dazeb/noctraos`) — this is a hard
requirement: the one-liner bootstrap and the ISO's first-boot fetch clone it
anonymously. Never make it private, never commit secrets.

## Repository map

```
proxmox-install.sh          one-command Proxmox VE installer: downloads the release qcow2 or ISO, checks it against
                            SHA256SUMS, builds a UEFI VM; NOCTRAOS_* env vars answer every prompt (README, docs/setup.md)
boot.sh                     remote fetcher: clones repo to ~/.local/share/noctraos,
                            runs install.sh; env: NOCTRAOS_REPO_URL, NOCTRAOS_BRANCH, NOCTRAOS_HOME
install.sh                  orchestrator: logging, TARGET_USER resolution, flags
                            (--skip-ai, --skip-gui, --skip-gpu, --only <module>), runs modules 00-11
install/
  lib.sh                    shared helpers: log/warn/die, as_user(), apt_install(),
                            desktop_file_exists(). Modules MUST source it.
  00_preflight.sh           user/sudo/OS/network/25GB-disk/RAM checks
  01_system.sh              apt core + python build deps, Flathub, Nerd Font
  02_mise.sh                mise binary, profile.d + bash.bashrc hooks, runtimes,
                            Herdr, Starship, lazygit, lazydocker
  02b_gpu_drivers.sh        GPU detect + NVIDIA driver/CUDA or AMD ROCm (thin wrapper
                            over bin/noc-gpu; before 03 so Ollama sees the GPU)
  03_ai_core.sh             Ollama + qwen2.5-coder:7b + nomic-embed-text
  03b_ollama_update.sh      Ollama to the newest upstream release (vendor installer pinned to it); not in the full run, root, via the panel
  04_gui_apps.sh            Microsoft VS Code (apt repo) + extensions, Mission Center,
                            CopyQ; retires codium/chatbox/foot (user data kept)
  04_workstation_apps.sh    Omarchy-style workstation app set: apt CLI/system tools + the Flathub GUI apps
  04c_app_policy.sh         Flatpak/AppImage-first policy: retires the apt copy of an app once
                            its Flatpak is in, retires unwanted base apps, hides junk launchers
  04d_appmanager.sh         AppManager (kem-a/AppManager): AppImage installer/updater, sha256-verified
                            release in /opt/appmanager; non-fatal; rerun: install.sh --only 04d_appmanager.sh
  05_mouse_ergonomics.sh    Nautilus right-click scripts
  06_desktop_theme.sh       gsettings ergonomics, wallpapers, Agents menu,
                            AI-first /etc/xdg/menus/gnome-applications.menu
  07_persistence.sh         /etc/skel defaults, noc + Control Panel install (retires the old noc-menu)
  08_shell_theme.sh         NoctraOS-Dark shell + GTK themes (derived, not
                            shipped), white menu icons, terminal/app palette
  09_super_search.sh        Super+Space search, Noctra start button and Start panel:
                            installs the three GNOME Shell extensions, search app,
                            schemas, help page, index timer, welcome/branding autostart
  10_boot_theme.sh          Plymouth splash + GRUB theme for non-ISO installs
                            (update-alternatives, update-initramfs, update-grub)
  11_hermes.sh              Hermes Desktop preinstalled (runtime + Electron app build),
                            free Nous tier primary, local Ollama fallback; runs LAST (25+ min, no sudo)
                            (module order in install.sh: 00 01 02 02b 03 04 04_workstation 04c 04d 05 06 08 09 10 07 11)
bin/
  noc                       CLI: update [--json] [--only ..] | updates | doctor [--json] | status | models [list [--json]|default|presets|pull|rm]
                            | skip [list [--json]|add|rm] | bg [list|next|set] | gpu. Sourceable (tests call its functions); NOC_OLLAMA_URL overrides the Ollama URL
  noc-gpu                   GPU detect [--json] | install | status [--json] (NVIDIA driver+CUDA, AMD ROCm); VERSION must match noc
  noctraos-control          wrapper that execs the system-Python Control Panel (control/)
  noc-accounts              first-time setup without a terminal: Git name/e-mail (`git config --global`) and the GitHub sign-in (`gh auth login --web`
                            device flow); `noc accounts ...`, the panel's Accounts page, the Overview card, a button in the Welcome app
  noc-upstream              tracks apps that come from their publisher's releases (Hermes, Ollama, AppManager, the coding agents):
                            installed vs newest release, version history, user-level updates; `noc apps`, the panel's Apps page
  noc-selfupdate            updates the NoctraOS layer itself (signed manifest + bundle, staged rollout, migrations, rollback);
                            installed to /usr/local/libexec/noctraos by module 07; check/status/notify/migrate user-side, apply/rollback as root
  noc-privileged            root side of the panel, run through pkexec: allowlisted `update apt,flatpak,noctraos`, `update-channel`, `update-rollback`, `module <name>`, `gpu-install <vendor>`
                            (installed to /usr/local/libexec/noctraos; policy in configs/polkit/)
  noctraos-hermes           Hermes Desktop launcher/installer: launch | local [--no-launch] | cloud | mode | install | ready | status.
                            Sets HERMES_GUEST_ONBOARDING=1 (free tier), seeds the Ollama fallback
  noctraos-welcome          first-run welcome (GTK; replaces Zorin's tour), --force/--provisioning
  noctraos-appearance       wallpaper + fonts panel (we fix theme/layout, so no theme switcher)
  noctraos-agent            agent launcher wrapper: installs npm package on
                            first use, then execs the agent
  noctraos-search           wrapper that execs the system-Python search app (search/)
  noctraos-copyq            CopyQ autostart wrapper: runs it under XWayland, sets the tray icon white
  noctraos-weather          Open-Meteo lookup for the Start panel (keyless; city is a user choice)
branding/setup-branding.py  once-per-account dock + top-bar layout (marker desktop-layout-v1)
extensions/                 GNOME Shell extensions: noctraos-search (Super+Space overlay),
                            noctraos-start (Start panel), noctraos-branding (flat top bar, Show Desktop)
control/                    Control Panel (docs/control-panel-plan.md): panel.py = pure formatting of `noc ... --json`
                            (unit-tested, no GTK), main.py = GTK3 window; installed to /usr/local/share/noctraos-control
search/                     search app: file index (SQLite), CopyQ bridge, browser history, settings window
help/index.html             "New users start here" page the Start panel opens
scripts/                    render-theme.py, build-desktop-theme.py, seed-password-store.py, make-update.py (update bundles + signed manifests)
migrations/                 system/ and user/ scripts a machine runs once when it updates (README has the rules); in the update bundle
configs/update/             update-signers: the PUBLIC update key every machine trusts (the private key never enters the repo)
tests/                      unittest: theme composition (test_desktop_theme), GPU detection (test_gpu_detect),
                            noc/noctraos-hermes JSON modes (test_noc_cli), Control Panel cards (test_control_core)
site/                       project website (static, deployed via wrangler.jsonc); keep claims in step with README
                            every page head carries canonical, Open Graph, Twitter and JSON-LD metadata; `script.js` also holds the screenshot lightbox (a
                            progressive enhancement of the `figure.shot > a` links, native `<dialog>`; tests/test_site_lightbox.py drives it in headless Chrome); social cards live in
                            site/img/social/ (1200x630), favicons/manifest/robots.txt/sitemap.xml/.well-known/security.txt in site/
scripts/render-social.py    renders the OG cards, the X promo images (assets/promo/x/) and the favicons with headless Chrome,
                            from assets/social/fonts (local woff2); rerun it when a page title or a screenshot changes
docs/launch/                launch copy: x-posts.md (the thread, standalone posts, alt text, length-checked)
.gitlab-ci.yml              the working CI (homelab GitLab, project dazeb/noctraos, Docker runner): shell checks, VERSION match,
                            unit tests, theme check. A pushed tag vX.Y.Z also runs release-build -> release-publish ->
                            release-site on the `noctraos-release` runner (docs/release-runbook.md). The site itself is
                            deployed by Cloudflare when GitHub main updates. Push to GitLab with `git push gitlab <branch>`
.github/workflows/ci.yml    shell + VERSION checks only; GitHub Actions does not run on this account
.agents/skills, skills-lock.json  vendored pstack agent skills (.claude/skills symlinks into them); not product code
configs/
  mise/config.toml          node=lts, python=3.12, go=latest, terminal tools
  vscode/                   settings.json, extensions.list, continue_config.yaml,
                            vscode.sources (Microsoft apt repo)
  copyq/copyq.conf          clipboard history preseed (1000 entries, silent, tray)
  autostart/                copyq, noctraos-welcome, noctraos-branding, noctraos-search-setup
  applications/             agent (incl. Hermes) + Herdr + Local-LLM + Welcome/Appearance launchers, .directory files
  hermes/onboarding.md      first-run prompt Hermes gets until ~/.hermes/.noctraos-onboarded exists
  gsettings/, systemd/      search and Start-panel schemas; the file-index user timer
  theme/                    palette.json (source of truth) + templates/remaps -> shell/GTK CSS, Herdr and btop palettes
  xdg/                      gnome-applications.menu (AI-first tree), agents merge
  nautilus-scripts/         "Open in VS Code", "Ask AI to Explain", "Open Terminal Here" (spaces, not
                            underscores: a menu label eats "_" as a mnemonic marker)
assets/
  wallpapers/               6 seeded 4K JPEG scenes + generate-wallpapers.py
  icons/                    white SVG glyphs (agents, Local LLM, category tiles)
  icons/overrides/          white SVGs under STOCK icon names — these replace
                            the system category icons system-wide; copyq.svg (+ overrides/hicolor/NxN PNGs)
                            replaces CopyQ's green icon with a white one
  icons/noctraos-theme/     small derived icon theme (inherits ZorinGrey-Dark)
assets/boot/                boot-chain artwork: plymouth/noctraos (two-step theme),
                            grub/noctraos (theme.txt + generated pixmaps/.pf2),
                            isolinux/ (splash + theme.cfg), generate-boot-assets.py
                            (outputs are committed; JetBrains Mono, OFL)
iso/strip-census.sh         sourced by the build script: removes Zorin's census (installer checkbox, cron jobs)
iso/rebrand-labels.sh       sourced by the build script: user-facing Zorin names (About, sessions, banner, launchers, live user)
iso/build-release.sh        release build: ISOs -> VM -> provisioned disk -> qcow2/vmdk/torrent/SHA256SUMS -> boot test (RELEASE_REHEARSAL=1 to try it)
iso/publish-release.sh      upload to dl.noctraos.dev, verify through the public hostname, create the GitHub release; never overwrites a version
iso/renew-update-channels.sh, setup-update-renewal.sh   weekly systemd user timer that re-signs the update manifests before
                            they expire (30 days); `setup-update-renewal.sh status` shows the real expiry of each channel
iso/publish-update.sh       rolling updates for installed systems: build/promote/renew a signed update on the nightly/stable channel,
                            both stores, read back and verified (docs/updates.md); needs ~/secrets/noctraos-update-signing
iso/vm-image.sh, r2-env.sh, boot-test-image.sh   shared by nightly and release: the VM provisioning, rclone env, exported-disk boot test
iso/setup-release-runner.sh doctor|install|status|remove the GitLab runner (user service, tag noctraos-release, protected refs) that runs the above
scripts/update-site-release.py, release-site-pr.sh, make-torrent.py   rewrite the site for a release, open+merge the PR, wait for the deploy
iso/bake-shell.sh           sourced by the build script: copies the Shell extensions, search app, schemas and the two setup
                            autostarts into the squashfs so the FIRST session has Super+Space and the Start panel
iso/boot-theme.sh           sourced by the build script: themes the extracted ISO
                            tree, the live initrd and the squashfs
iso/initrd-theme.py         swaps the Plymouth theme inside casper/initrd.zstd
iso/build-noctraos-iso.sh   ISO remaster pipeline (runs on the Proxmox node);
                            NOCTRAOS_UNATTENDED=1 + NOCTRAOS_USER/PASSWORD/…
                            bake an unattended-install seed and boot entries
iso/preseed/noctraos.seed.in  Ubiquity/d-i seed template for the above
iso/build-local.sh          build the release (and appliance) ISO on a fast workstation in a privileged
                            Docker container, work dir an ext4 image on a big drive; ~2 min per ISO;
                            fails if a release ISO has a seed or unattended entry
iso/local-vm.sh             local KVM test VM: start/stop, console screenshot, absolute clicks, keys,
                            ssh/scp. No root, no host changes
iso/pve-console-shot.py     console frames from a Proxmox VM via the API (boot-testing without a shell)
docs/                       objectives (source of truth), onboarding, desktop-layout, control-panel (+ -plan), theme-design,
                            omarchy-parity, release-runbook
docs/release-runbook.md     ORDERED HANDOFF for shipping 0.3.0: rebuild, test, VM disk, upload, tag
iso/vm-sysprep.sh           run inside a fully provisioned VM before exporting its disk as a
                            downloadable image: strips machine id, SSH host keys, Hermes
                            identity/history, logs; refuses to run on bare metal
```

## Non-negotiable rules

1. **Never run `install.sh`/`boot.sh` on the local dev workstation.** This box
   (Ubuntu 26.04, `dazeb-ubuntubox`) is for editing and static checks only.
   All runtime testing happens in a test VM: the local KVM VM (`iso/local-vm.sh`,
   the fast test bed) or the Proxmox test VM.
2. **Every module must be idempotent.** Guard every mutation (`command -v`,
   file existence, `dpkg-query`, `gsettings get`). Re-running install.sh must
   be a no-op. There is a live test VM precisely to prove this.
3. **Desktop settings are warn-not-die.** `gsettings`/theme steps must never
   abort an install (`|| warn "..."`). Core steps (apt, ollama) may die.
4. **`gs` is a trap.** Module 06 defines a local `gs()` helper for gsettings.
   Other modules must NOT call bare `gs` — it resolves to the **Ghostscript
   binary**. Use `as_user gsettings set ...` explicitly.
5. **No `grep -q` on pipes under `set -o pipefail`** for large-output
   producers (`fc-list`, …): grep exits early, SIGPIPEs the producer, and the
   guard misreads "installed" as "missing". Drain with `grep ... >/dev/null`.
6. **gsettings must target the user session bus**, never `dbus-launch`:
   `as_user` in lib.sh handles it (DBUS_SESSION_BUS_ADDRESS=/run/user/UID/bus).
7. **Verify pushes server-side**: `gh api repos/dazeb/noctraos/commits/heads/main --jq .sha`.
   A clean `git push` exit code has already lied here once — check which branch
   HEAD is on (`git status`) and confirm the remote SHA after pushing.
8. **Working tree hygiene**: commit on `main`. If `git status` shows a feature
   branch you did not intentionally create, stop and reconcile before
   committing (this bit us: 6 commits landed on a stray branch unnoticed).
9. **Do not touch other guests on the Proxmox node** (VMs 107/108/113/114,
   LXC 100-112/200/210). VM 114 (`zorin-ai-iso-test`) is ours.
10. **Nautilus scripts get selections via env vars**
    (`NAUTILUS_SCRIPT_SELECTED_FILE_PATHS`), not argv. VNC-typed text into the
    guest loses shifted characters (`& @ > :`) — route anything complex
    through SSH or an HTTP fetch from port 80 (no colon in URL).

## Environment (infrastructure)

- **Proxmox node**: `ssh root@192.168.8.195` (key auth, host "files",
  PVE 9.2.20, i7-4770K / 15 GiB RAM). Web-UI password unknown — work over SSH.
- **Test VMs**: VM 110 `zai-zerotouch-test` at `192.168.8.138` (v0.3 zero-touch
  reference; DHCP — re-scan if the lease moved) and VM 114 `zorin-ai-iso-test`
  at `192.168.8.187` (v0.2 reference). User `dazeb`, password
  `zorin-test-2026` (throwaway), our SSH key authorized on both, passwordless
  sudo via baked NOPASSWD (110) / `/etc/sudoers.d/zai-test` (114).
- **Remote testing from a cloud/CI agent (Tailscale)**: the LAN IPs above are
  not routable from outside. VM 114 is on the tailnet as `zorin-ai-iso-test`
  (`100.125.207.0`); the node is `files` (`100.83.252.94`). Nothing advertises
  `192.168.8.0/24`, so use the tailnet IPs. A cloud container has no TUN-based
  routing, so run Tailscale in userspace mode and SSH through it:
  ```bash
  tailscaled --tun=userspace-networking --state=$S/tailscaled.state --socket=$S/ts.sock &
  tailscale --socket=$S/ts.sock up --auth-key=<ephemeral, tagged key> --hostname=claude-cloud
  ssh -o ProxyCommand="tailscale --socket=$S/ts.sock nc %h %p" dazeb@100.125.207.0
  ```
  Start `tailscaled` with `setsid nohup` (plain background jobs die between
  turns; saved state rejoins without the key). Needs `openssh-client`. Auth
  keys are pasted by the user per session — never commit one, and ask the user
  to revoke it afterwards. The agent's SSH public key must be in VM 114's
  `~dazeb/.ssh/authorized_keys`; do not add keys to or touch the Proxmox node.
  Verified 2026-10-04: static checks, full `install.sh` run + idempotent
  second run, and `noc doctor` all green on VM 114 this way.
- **API-only access to the node** (no shell): a Proxmox API token (`root@pam!claude`) over
  `https://192.168.8.195:8006` works from the cloud container once the home router
  advertises `192.168.8.0/24` to the tailnet and the container runs
  `tailscale set --accept-routes`; run `tailscaled --tun=userspace-networking
  --socks5-server=localhost:1055` and curl with `-x socks5h://localhost:1055` (clear
  `no_proxy`, or curl bypasses the SOCKS proxy). Uploads go through that relayed tunnel at
  ~1 MB/s, so a 3.6 GB ISO takes about an hour. Boot-testing without a shell: create a
  throwaway VM via the API (UEFI, ISO on `ide2`), grab frames with
  `iso/pve-console-shot.py`, then delete the VM. ISOs for this are kept in the
  `noctraos-isos` directory storage (`/local-zfs/noctraos-isos`; `local` has no room). The
  node has ~4 GiB free RAM: one 3 GiB test VM at a time, nothing else.
- **Hetzner Object Storage release bucket** (created 2026-10-08): `noctraos-releases` in Falkenstein, S3 endpoint
  `https://fsn1.your-objectstorage.com`, public base `https://noctraos-releases.fsn1.your-objectstorage.com`
  (anonymous GET and Range verified; the bucket root lists as 403). Credentials: `~/secrets/noctraos-s3.env`
  (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`), never print them. `iso/publish-release.sh` publishes there with
  `RELEASE_STORE=hetzner` (default stays `r2` = dl.noctraos.dev); `store_env` in `iso/r2-env.sh` does the switch. The site,
  `proxmox-install.sh` and `scripts/release-site-pr.sh` still point at `dl.noctraos.dev`, so a Hetzner-only publish is not
  yet what downloaders get: moving the canonical URL (custom domain or a redirect) is a separate decision.
- **Rolling updates of the NoctraOS layer** (built 2026-10-08, `docs/updates.md`): `noc update` step `noctraos` runs
  `/usr/local/libexec/noctraos/noc-selfupdate apply`. Rules: (1) the item list in `install/07_persistence.sh`, `BUNDLE_ITEMS`
  in `bin/noc-selfupdate` and `ITEMS` in `scripts/make-update.py` must stay equal (a test pins it), (2) migrations are
  idempotent and additive (`migrations/README.md`), (3) never give the updater or `noc-privileged` a path, URL or command
  from the caller, (4) the private key `~/secrets/noctraos-update-signing` is used only by `iso/publish-update.sh` on the
  release workstation, (5) a published bundle `updates/bundles/noctraos-N.tar.gz` is never replaced: publish the next serial,
  (6) manifests expire after 30 days: the weekly timer from `iso/setup-update-renewal.sh` renews both channels; check it with
  `iso/setup-update-renewal.sh status`, and never switch the workstation off for a month without renewing by hand.
  Not wired into the tag pipeline yet; machines installed from 0.3.2 or earlier need the one-line installer once to get the updater.
- **VM disks and ISO scratch go on the fastest local disk** (rule from the user, 2026-10-08). `iso/disks.sh` picks it:
  the candidates in `NOCTRAOS_DISK_CANDIDATES`, best first, the first that is a real Linux filesystem (never NTFS/FAT/tmpfs)
  with enough free space. Measured with `iso/fastest-disk.sh` on 2026-10-08: the Crucial P310 2 TB (`/run/media/dazeb/2tb`) writes 2.2 GB/s
  and reads 2.8 GB/s; the Samsung 960 PRO (`/mnt/nvme1`) 0.6 to 1.1 GB/s and 2.3 GB/s, so the 2 TB drive is first. Re-measure after
  hardware changes (when no build runs). `build-release.sh` fails in seconds if the VM disk drive has under 100 GB free.
  Keep cold data off `/mnt/nvme1` with `~/workspace/shared/scripts/offload-dir.sh <dir>` (copy, checksum-verify, symlink).
- **Every setup chore is skippable and every action has a terminal tip** (user's rule, 2026-10-09: "mouse first, terminal a close second"). A
  chore the panel offers (Git identity, GitHub sign-in, GPU setup) has a "No, I'll set it up myself" button that runs `noc skip add <id>`
  (the one store, `~/.config/noctraos/skipped`; `noc status --json` carries it as `skipped`), after which nothing nags (Overview card, page
  headline, Welcome app) and the page shows the commands instead. Every action page has a quiet *Terminal* button whose tooltip lists the
  commands (`TERMINAL` in `control/panel.py`; a test checks each command exists). Never show a command to someone who did not ask for it:
  commands live behind hover/click, or in the place of a chore the person declined. A new chore needs: an id in `SKIPPABLE` (`control/panel.py`
  and `bin/noc`), the skip button and a skipped state on its page, a `TERMINAL` entry; the Welcome app repeats the Git/GitHub commands as text
  (a test pins them to `TERMINAL`).
- **Accounts setup is for people who are not developers** (user's rule, 2026-10-08: "they just want AI and they want it to work"). Never
  make Git or GitHub setup need a terminal, a token or a command to copy. `noc-accounts` runs `gh auth login --web` with prompts off
  (stdin closed, `GH_PROMPT_DISABLED=1`; it prints a one-time code and a URL and then waits, no Enter needed), strips `GH_TOKEN` and
  `GITHUB_TOKEN` from its environment (gh refuses to log in while they are set), runs `gh auth setup-git` so `git push` works, and offers
  GitHub's private `ID+login@users.noreply.github.com` address (pushes that would reveal a private address are rejected). It never reads or
  prints a token. Local status reads `~/.config/gh/hosts.yml`; `--verify` asks GitHub. The sign-in subprocess is stopped with SIGTERM
  (Cancel); its timer thread must stay a daemon or the program will not exit.
- **Upstream apps follow the newest published release** (2026-10-08, `docs/updates.md`): `bin/noc-upstream` is the only place that
  resolves "latest" (GitHub `releases/latest`, npm `latest`; never a prerelease or a branch tip). Hermes: do not use
  `hermes update --branch <tag>` (it treats the tag as a branch and fails) or `hermes update --channel stable` (not published,
  HTTP 404); `noctraos-hermes install|update` pin the official installer to the release tag and swap the runtime directory, and
  restore it on failure. The installer is coupled to current code: an old tag (v2026.9.14, v2026.9.24) fails with it, so
  never pin to a release older than the installer expects. The installer's own re-run path only fetches branches. Root-owned
  apps (Ollama, AppManager) are updated only by allowlisted modules in `noc-privileged`'s `MODULES`.
- **Preferred ISO build is local** (`iso/build-local.sh`, see docs/release-runbook.md): about 2
  minutes versus 35 to 45 on the node. Building on the node loads the HDD pool that the test VMs
  live on and crashed VM 114 once; do not run builds and VMs on the node at the same time.
- **ISO build** can still run on the node (older flow, kept for reference). Scratch MUST be on
  `/local-zfs` (`WORK_BASE=/local-zfs/iso-build`) — pve-root has ~8 GiB free
  and the build needs ~25 GiB. The zfs pool is HDD-backed: unsquashfs and
  mksquashfs take 10-20 min each; total build ~35-45 min. Run as a
  `systemd-run --unit=<name> --collect bash -c "..."` unit (plain nohup over
  ssh dies with the session). ISOs live in `/var/lib/vz/template/iso/`.
- **RAM pressure**: the node juggles 14 GiB of allocated VMs. Don't start
  extra VMs while builds run; builds peak ~2 GiB.
- **local-zfs is nearly full** (~17 GiB free, 2026-09-26): a build's scratch
  (~15 GiB peak) fits, but delete `noctraos-iso-build.*` work dirs afterwards.
- `xorriso`, `git`, `squashfs-tools`, `openssl` are available on the node.
- **Unattended ISO build** (v0.3+): the build script clones the provisioner
  from GitHub for the squashfs, so push first; the seed template is read from
  the script's own `iso/preseed/` dir. Unattended builds imply autologin +
  NOPASSWD sudo for the created user. **A release build is the same command
  without `NOCTRAOS_UNATTENDED`**: no seed, no password hash, no unattended boot
  entry (an unattended entry wipes the disk without asking). VERSION must match
  `bin/noc`; the output is named `noctraos-<VERSION>-amd64.iso`.

## Commands

```bash
# static checks (docker shellcheck — not installed on this host)
bash -n boot.sh install.sh install/*.sh bin/noc bin/noc-gpu bin/noc-privileged bin/noctraos-control bin/noctraos-agent \
  bin/noctraos-copyq bin/noctraos-hermes bin/noctraos-search configs/nautilus-scripts/*     # other bin/ files are Python
docker run --rm -v "$PWD:/mnt" koalaman/shellcheck:stable --severity=warning \
  boot.sh install.sh install/*.sh bin/noc bin/noc-gpu bin/noc-privileged bin/noctraos-control bin/noctraos-agent \
  bin/noctraos-copyq bin/noctraos-hermes configs/nautilus-scripts/*     # same list as CI
python3 -m unittest discover -s tests                # 344 tests: theme, GPU detection, noc JSON modes, root helper, Control Panel
python3 scripts/render-theme.py --check              # committed theme outputs match palette.json

# wallpaper iteration (venv at ~/workspace/scratch/zorin-img-venv: pillow+numpy)
cd assets/wallpapers
~/workspace/scratch/zorin-img-venv/bin/python generate-wallpapers.py \
  --width 1920 --height 1080 --outdir /tmp/wp-preview     # fast previews
~/workspace/scratch/zorin-img-venv/bin/python generate-wallpapers.py      # 4K final

# deploy a change to the test VM (idempotent full pass)
tar czf /tmp/noctraos-repo.tgz --exclude=.git --exclude=.zcodeignore .
scp -q /tmp/noctraos-repo.tgz dazeb@192.168.8.187:/tmp/
ssh dazeb@192.168.8.187 'rm -rf ~/.local/share/noctraos && mkdir -p ~/.local/share/noctraos \
  && tar xzf /tmp/noctraos-repo.tgz -C ~/.local/share/noctraos \
  && nohup bash ~/.local/share/noctraos/install.sh > /tmp/noctraos-run.log 2>&1 &'
# headless runs need NOPASSWD sudo (already enabled on VM 114) or cached creds

# fresh-clone audit + server-side push verification
git clone -q git@github.com:dazeb/noctraos.git /tmp/noctraos-clone && find /tmp/noctraos-clone -type f | wc -l
gh api repos/dazeb/noctraos/commits/heads/main --jq '.sha[0:7] + " " + .commit.message'

# ISO build (on the node — clone fresh so the baked snapshot + seed match main)
ssh root@192.168.8.195
git clone -q --depth 1 https://github.com/dazeb/noctraos.git /local-zfs/iso-build/noctraos-src
systemd-run --unit=noctraos-iso --collect bash -c \
  "NOCTRAOS_UNATTENDED=1 NOCTRAOS_USER=dazeb NOCTRAOS_PASSWORD=zorin-test-2026 \
   WORK_BASE=/local-zfs/iso-build bash /local-zfs/iso-build/noctraos-src/iso/build-noctraos-iso.sh \
   /var/lib/vz/template/iso/Zorin-OS-18.1-Core-64-bit.iso \
   /var/lib/vz/template/iso/noctraos-18.1-amd64.iso > /root/noctraos-build.log 2>&1"
tail -f /root/noctraos-build.log
```

## Known pitfalls (each cost real debugging time)

- **xorriso refuses non-empty `-outdev`** ("media holds non-zero data"):
  the build script `rm -f`s the previous ISO before writing. Do not remove
  that line; do not silence xorriso's output.
- **`sudo -v` needs a TTY even under NOPASSWD sudoers** — headless preflight
  uses `sudo -n true` first. Keep that fallback order.
- **VS Code replaced VSCodium (b6981b4); Chatbox and Foot are retired.**
  Module 04 installs `code` from Microsoft's apt repo (key in
  `/usr/share/keyrings/microsoft.gpg`, source from `configs/vscode/vscode.sources`;
  `debconf-set-selections` stops the package adding its own repo), then
  `apt-get remove`s `codium`, `chatbox`, `xyz.chatboxapp.app` and `foot` — never
  purge/autoremove, user data stays. Legacy `Open_in_VSCodium` Nautilus scripts
  are deleted by modules 05/07. Settings and Continue config are only seeded
  when missing, so existing installs keep their old copies.
- **Top bar + dock come from settings, not patches.** `branding/setup-branding.py`
  (once per account, marker `desktop-layout-v1`) turns on the Zorin Taskbar's
  `stockgs-keep-top-panel`, makes it a centred dock (`panel-lengths` -1) and trims
  its elements; `noctraos-branding` adds Show Desktop and flattens the top bar.
  To change the layout for an existing account, delete the marker and re-run the
  script (or edit the taskbar settings).
- **The Start panel hooks a private Zorin Menu API.** `noctraos-start` replaces the
  Start button's popup (`menuButtons[i]._menu.toggle/open`). It takes a modal grab
  on a full-screen root actor and decides "outside click" by pointer coordinates —
  `event.get_source()` is null for clicks on the root and a stage-level
  `captured-event` handler never fires under a grab. Both were tried and failed.
- **CopyQ's tray icon ignores the icon theme.** It is drawn from CopyQ's own resources, so the white
  override in `assets/icons/overrides` only reaches its window/app icon. The AppIndicator `custom-icons`
  setting does not help either (the original image still shows through under the custom one). Instead
  `noctraos-branding` tints that one tray icon (indicator id `CopyQ_copyq`, `MONO_TRAY_IDS`) with a
  `Clutter.ColorizeEffect` in the colour of the neighbouring status icons, read from the theme, so it follows
  theme changes (verified on the VM by recolouring the status icons: CopyQ followed). `bin/noctraos-copyq`
  also sets the session `iconColor` white (not saved) so the rings tint at full strength.
- **CopyQ must run with `QT_QPA_PLATFORM=xcb`.** As a native-Wayland client it
  logs "Failed to activate Wayland clipboard" and records nothing on GNOME
  (no wlr-data-control). The autostart entry sets it; keep it that way.
- **Plymouth two-step loops `throbber-*.png`, not `animation-*.png`.** `animation-`
  frames are only the end-of-boot animation, so a theme that ships only those shows
  a blank screen. Also: `UseProgressBar=true` in `[boot-up]` replaces the throbber
  with a bar. The live initrd contains only the `two-step` module (no `script.so`),
  so any custom theme must be two-step. Fonts available there: Ubuntu / Ubuntu Mono.
- **The live boot verifies `/cdrom/md5sum.txt`** (`casper-bottom/01integrity_check`,
  skippable with `fsck.mode=skip`) and prints "errors found" for every file we
  changed. The build script used to write `md5sums.txt` (plural) and hash the
  *extracted original* squashfs, so the list was always wrong; it now moves the new
  squashfs into the tree first and writes `md5sum.txt`.
- **GRUB gfxmenu ignores a `progress_bar`'s `height`** (it drew a 28 px slab whatever
  was set), so the theme shows a text countdown (`label` with `id = "__timeout__"`)
  instead. isolinux: an opaque `MENU COLOR screen` background hides
  `MENU BACKGROUND`'s image — make it `#00000000`.
- **Testing boot screens without the node**: download the Zorin ISO from a mirror
  (zorin.com/os/mirrors lists them), stage only the boot pieces with
  `iso/boot-theme.sh` onto a copy (`xorriso -indev … -outdev … -boot_image any replay
  -map …`, no squashfs repack), then boot it under `qemu-system-x86_64` (no KVM needed)
  and take `screendump`s over the monitor socket. UEFI needs OVMF and ~50 s under TCG;
  set `timeout=300` in the test copy of grub.cfg or the menu is gone before the shot.
  Plymouth themes can be previewed with `plymouthd --no-daemon` under Xvfb with
  `--kernel-command-line="splash plymouth.ignore-serial-consoles"` (needs the
  `plymouth-x11` and `plymouth-theme-spinner` packages).
- **The installer takes its name from `/cdrom/.disk/info`** (`Zorin-OS 18.1 Core 64bit`, hyphen):
  ubiquity's `get_release()` uses the first word, hyphen turned into a space, for
  "Try/Install ${RELEASE}". The old `sed 's/Zorin OS/…/'` never matched; it is now
  `s/^Zorin[- ]OS/NoctraOS/`. The two pictures on that page are
  `usr/share/ubiquity/pixmaps/{cd_in_tray,ubuntu_installed}.png`.
- **Clamp every radius spelling, not just `border-radius`.** Zorin rounds headerbars and titlebars with
  `border-top-left-radius: 15px` and the `-gtk-outline-*-radius` variants. `scripts/build-desktop-theme.py`
  only clamped `border-radius:`, so with `radius: 0` the window frame was square but the headerbar corner
  stayed round and showed as a dark wedge at the top-left of every GTK3 window (Welcome, Software Updater).
  The clamp now covers the per-corner longhands too (`RADIUS_DECLARATION`; tests pin it).
- **GNOME Shell scans for extensions once, at start.** Anything the first-boot provisioner installs into
  the running session is invisible until the next login on Wayland, so the extensions, schemas, search app
  and setup autostarts are baked into the squashfs (`iso/bake-shell.sh`, tests/test_bake_shell.py). Module 09
  still installs them (a no-op on a baked image) for `boot.sh` installs on an existing system, where the
  sign-out/in is still needed. Keep the file lists of the two in step.
- **Zorin's theme defaults live in `:zorin` session groups** (e.g.
  `[org.gnome.desktop.interface:zorin] gtk-theme`, `[org.gnome.shell.extensions.user-theme:zorin] name`
  in `50_zorin-desktop-session.gschema.override`), and a session group beats a plain
  group. A gschema override that only sets the plain group is silently ignored for the
  theme keys (the wallpaper keys have no `:zorin` entry, so those did apply). The ISO's
  `90_noctraos-live.gschema.override` therefore repeats the `:zorin` group names.
- **Autologin leaves the login keyring locked**, so apps that use the Secret
  Service (Hermes Desktop, browsers, VS Code) show an "Authentication required"
  prompt on first use: the keyring is encrypted with the account password, which
  an autologin session never types. `scripts/seed-password-store.py` (modules 04
  and 07) therefore replaces the user's login keyring with an **unencrypted** one
  (`~/.local/share/keyrings/login.keyring` plus `default`) when it is missing or
  empty (about 105 bytes), then module 04 restarts `gnome-keyring-daemon` so it
  re-reads it. `Unlock` then returns at once with no prompt, for every app. A
  keyring that holds secrets, or one in a format we do not recognise, is never
  touched. It also still adds `--password-store=basic` for Chromium (Flatpak) and
  `"password-store": "basic"` for VS Code. Trade-off, accepted: secrets are stored
  without a password, like the flags always did. Passing `--password-store=basic`
  to Hermes' Electron (`desktop.electron_flags`) does **not** stop its prompt
  (checked: the flag was on the process and the dialog still came), so do not
  go that way. Existing keyrings that hold secrets keep prompting on autologin.
- **Search indexes the home folder, not `/`.** `roots` defaults to `['~']`. With `/` the
  index filled with system paths (`/usr/lib/...`, Flatpak assets) that outranked the user's
  own files. `/` is still available in Search settings. A user who saved their own `roots`
  keeps it. Nautilus script files are named with plain spaces: a menu label eats `_` as a
  mnemonic marker ("AskAItoExplain").
- **Driving the VM desktop for tests**: over SSH, unlock the session
  (`gdbus call ... org.gnome.ScreenSaver.SetActive false`), take screenshots with
  `gnome-screenshot -f`, inject keys through `/dev/uinput` (needs sudo). Never
  `pkill -f <pattern>` in an ssh one-liner — it kills your own shell.
- **`zorin-menu.desktop` does not exist on Zorin 18**; favorites and menu
  code skip missing desktop entries by design.
- **`org.gnome.desktop.interface accent-color` key is absent** on Zorin 18.1 —
  the attempt warns and moves on.
- **Menu tree changes need a session rescan** (logout or reboot). Wayland has
  no in-place shell restart.
- **VNC typing into the VM console drops/mangles shifted characters** and
  rapid reconnects fail silently; vncdotool exit codes are always 1. Prefer
  SSH once sshd is up; use QEMU monitor `sendkey` for exact console input.
- **The first-boot runner falls back to the baked snapshot when `git` is
  absent** (fresh installs). Provisioner now installs openssh-server in
  module 01 for post-install remote access.
- **Unattended preseed: the first Ubiquity page stops the flow** — the
  "Updates and other software" page waits for Continue unless
  `ubiquity/download_updates`, `ubiquity/use_nonfree` and the Zorin-specific
  `ubiquity/no_zorin_os_census` are all preseeded (found in
  `usr/lib/ubiquity/plugins/ubi-prepare.py`, not in ubiquity.templates).
- **The GDM greeter is broken on Zorin 18.1**: gdm starts, the greeter's
  gnome-session cannot resolve ANY required component (org.freedesktop.systemd1
  activation fails on the greeter's private bus) → boot hangs at the splash
  forever. User sessions are fine. Unattended builds therefore default to
  autologin (writes /etc/gdm3/custom.conf in the squashfs).
- **Boot-test VMs must boot the disk first** (`--boot order="scsi0;ide2"`):
  after the unattended install reboots, a cdrom-first VM boots the installer
  ISO again instead of the new system.
- **casper waits for "remove installation medium, press ENTER"** unless the
  kernel cmdline has `noprompt` (see `casper-stop` in the squashfs) — the
  unattended boot entry carries it, so the installer auto-ejects and reboots.
- **sudo credentials expire mid-provisioner-run** (~15 min tty ticket): the
  firstboot flow blocks at the next sudo prompt. Autologin builds bake
  NOPASSWD sudoers; interactive first boots are fine (user is watching).

- **GPU module (`bin/noc-gpu`)**: the driver comes from Ubuntu (`ubuntu-drivers`,
  signed, no DKMS) and ONLY the CUDA toolkit from NVIDIA's repo; the pin file
  `noctraos-cuda-toolkit-only` blocks that repo's driver packages — never remove
  it (mixed Ubuntu/NVIDIA `libnvidia-*` breaks the driver). It is written BEFORE the
  repo is registered and a failed write aborts (`write_apt_file`); AMD models that are
  not positively recognised default to Vulkan, never to a ~15 GiB ROCm install. Module 02b must run
  BEFORE 03: Ollama's installer exits early only if `nvidia-smi` exists, else it
  installs NVIDIA's DKMS `cuda-drivers` over ours. CUDA 13 dropped
  Maxwell/Pascal/Volta, so those stay on driver 580 + CUDA 12.9. NVIDIA's debs do
  not create `/usr/local/cuda`; `ensure_cuda_symlink` does.
- **GPU testing**: test VMs have no GPU, so they only prove the "no GPU → skip,
  idempotent" path. Real coverage = `python3 -m unittest discover -s tests`
  (fixture lspci via `NOC_GPU_LSPCI_FILE`, `--dry-run`) plus a disposable
  `ubuntu:24.04` container for the AMD/apt path. The NVIDIA driver step needs real
  hardware; on this dev box `noc gpu install --dry-run` is safe (it detects the
  active driver + manual CUDA 13.3 and touches nothing).

- **Root work in the Control Panel goes through `bin/noc-privileged` and nothing else.** pkexec runs
  `/usr/local/libexec/noctraos/noc-privileged` (polkit action `dev.noctraos.privileged`, `auth_admin_keep`:
  one prompt for several calls). It is an allowlist of fixed verbs: `update apt,flatpak` execs the
  root-owned `/usr/local/bin/noc update --json`, and `module <name>` re-runs only the modules in its
  `MODULES` array. Modules are run from the **root-owned snapshot** `/usr/local/share/noctraos/repo`
  that module 07 refreshes, NEVER from `~/.local/share/noctraos` (a user-writable clone would be a
  root escalation). Add a module to `MODULES` only if it is idempotent and safe unattended; extend
  `tests/test_noc_privileged.py` with it. Never add a verb that takes a path, a command line or a
  package name from the caller. The Updates page runs root steps first (one prompt), then the user's
  own steps through `noc update --json`; it never uses a bare `sudo` and has no cancel for apt (a
  half-finished upgrade is worse than a slow one).
- **GPU setup in the Control Panel is never automatic.** The Hardware page shows what `noc-gpu` found,
  then a consent dialog (what gets installed, rough download size, restart/re-login needs, a free-disk
  check) and only on "Install" runs `pkexec noc-privileged gpu-install <nvidia|amd|all>`, which execs the
  root-owned `/usr/local/bin/noc-gpu install --vendor X` for the invoking user. It never offers an
  install over a pending reboot or for a too-old NVIDIA card. `noc-gpu status --json` rows are parsed
  back out of the normal text output, so keep the `OK`/`!!`/`..` markers. The sizes in
  `panel.GPU_NEEDS` are estimates shown as "about".
- **Privacy page rules**: the Nous free tier is a cloud service and the page must never say otherwise;
  switching to cloud needs an explicit confirmation; a user's own Hermes provider (`mode: other`) is
  never touched; `noctraos-hermes local --no-launch` switches without opening the app.
- **The Control Panel is a GUI for `noc`, nothing more.** `control/main.py` calls `noc ... --json`
  on a thread (`background()`), never blocks GTK, and every page needs a "not ready yet" state
  (Ollama down, no network) rather than an exception. Put anything that can be tested without
  GTK in `control/panel.py`. A card is only clickable when its sidebar page exists.
- **One default model, one file.** `noc models default <name>` writes `~/.config/noctraos/model`;
  precedence everywhere is `NOCTRAOS_MODEL`, then that file, then `qwen2.5-coder:7b`. The Welcome
  app, `noctraos-hermes`, "Ask AI to Explain" and (by rewriting its `    model:` lines) the seeded
  Continue config read it, each with the same few lines of inline lookup: change them together.
  `install/03_ai_core.sh` still installs the shipped model (the file does not exist yet).
- **`noc ... --json` is a contract for the Control Panel** (`docs/control-panel-plan.md`): keep the
  keys of `doctor --json`, `status --json`, `models list --json`, `models presets --json` and the
  `update --json` event stream stable (tests/test_noc_cli.py pins them). In JSON mode `noc update`
  uses `sudo -n`, so a missing credential fails with a message instead of hanging with no TTY.
- **A real AMD GPU test VM exists on TrueNAS** (`192.168.8.111`, VM id 1 `noctraosgputest`, created
  2026-10-06; manage it with `midclt call vm.start|vm.stop 1` over `ssh root@192.168.8.111`). It has the
  Radeon RX 580 (Polaris, `0a:00.0`, already on vfio-pci with its audio function and a clean IOMMU
  group) passed through, 4 vCPU / 8 GiB, a 64 GiB zvol `ssdpool0/noctraos-gpu-test` holding a
  provisioned NoctraOS disk, and a macvlan NIC (the NAS itself cannot reach it; other LAN hosts can;
  DHCP, find it by MAC `00:a0:98:71:01:df`). User `noctraos`/`noctraos`. Verified there: `noc gpu detect`
  picks the Vulkan tier, `noc gpu install --vendor amd` installs Mesa Vulkan and is a no-op the second
  time, `vulkaninfo` shows RADV POLARIS10, and Ollama with `OLLAMA_VULKAN=1` runs qwen2.5-coder:7b 100%
  on the GPU (29/29 layers). Not covered: ROCm (Polaris has none) and NVIDIA. Do not start it
  while the NAS is under memory pressure (it takes 8 GiB); stop it when done. The dev workstation's
  RTX 3080 Ti drives the desktop, so it cannot be passed through without ending the session.
- **Hermes' free tier is a cloud service: prompts leave the machine.** Everything the welcome app
  and README say about "local AI" is about the Ollama model; Hermes resolves to the Nous cloud
  unless it is local-only. Never describe Hermes as local without that qualification. The welcome
  app discloses it and offers `noctraos-hermes local` (Ollama primary, free tier off, persistent;
  undo with `noctraos-hermes cloud`, which refuses to touch a provider the user set). `noctraos-hermes ready` (runtime and app
  built) gates the Hermes buttons so they cannot start a second installer during provisioning.
- **Hermes free tier is gated and pre-GA.** The Nous free tier only exists when
  `HERMES_GUEST_ONBOARDING=1` (or `--guest-onboarding`); `noctraos-hermes` exports it. Never
  set `model.provider` for the user: an explicit provider beats the free tier in
  `resolve_provider`, and a bare `fallback_providers` entry does not rescue a machine that has
  no identity and no network (no_provider_configured fires first), which is why the wrapper makes
  Ollama the primary only in that offline-first-launch case. Upstream disabled Linux desktop
  release builds, so module 11 builds the app locally with `hermes desktop --build-only`; write
  config with `hermes config set`, never by editing config.yaml. Verified on VM 114
  (2026-10-04): free tier resolves to `provider=nous` / `nous/welcome` with no signup.
  `model.provider: "auto"` is Hermes' stock default and is NOT an explicit choice
  (`explicit_provider` in the wrapper treats auto/empty as unset).
- **Hermes onboarding prompt** (`configs/hermes/onboarding.md`): the wrapper exports it as
  `HERMES_EPHEMERAL_SYSTEM_PROMPT` until `~/.hermes/.noctraos-onboarded` exists (the prompt
  tells the agent to create it). There is deliberately no separate greeting turn: Hermes Desktop
  opens with its OWN guided intro ("what should I call you?", "Skip setup"; hardcoded in
  `apps/desktop/src/i18n/en.ts`, no supported off switch found), so the prompt starts the tour
  from the user's first reply instead. The conversation is: who the user is (saved to
  USER.md via the memory tool, target `user`; ~1,375 char cap), who the agent should be (a
  "## How I should be" section appended to `~/.hermes/SOUL.md`, text shown first; SOUL.md is a
  protected instruction file, so Hermes asks the user to approve the write), then only an
  OFFER of the tour, run on a yes. Declining or finishing creates the done marker. A one-shot `hermes chat --oneshot` greeting was tried first:
  it works but must pass `--source desktop` (the default source `oneshot` is hidden from the
  desktop's session list) and it never showed ahead of Hermes' own intro. A `hermes config set`
  value that starts with `--` is parsed as a CLI option, so pass lists as JSON (`'["--flag"]'`).
- **Hermes Desktop on a VM renders blank unless Electron gets `--no-sandbox
  --disable-dev-shm-usage`** (renderer crash loop, `/dev/shm ... No such process`); the wrapper
  seeds them via `desktop.electron_flags` when `systemd-detect-virt` says VM. Launching over SSH
  also needs the Xwayland auth file (`/run/user/1000/.mutter-Xwaylandauth.*`) and
  `env -u SSH_CONNECTION -u SSH_CLIENT -u SSH_TTY` (Hermes disables the GPU for "remote display").
  The Hermes runtime + app build adds ~5 GiB; a second `install.sh` on VM 114 then fails the
  25 GiB free-space preflight (24 GiB free) — run single modules instead.
- **Never run `hermes config set` with a temp `HERMES_HOME` on a box that has Hermes
  installed:** it regenerates the shared launcher in the checkout
  (`~/.hermes/hermes-agent/.hermes/bin/hermes`) pointing at the temp tools dir.

- **App policy: Flatpak and AppImage first** (`install/04_workstation_apps.sh` lists the
  Flatpaks, `04c_app_policy.sh` does the rest). apt is for CLI tools, system tools and
  host-integration apps (VS Code, CopyQ, Docker). Retirements simulate `apt-get -s remove`
  first and skip if apt would also remove a protected package (zorin-os*, gnome-shell, …);
  launchers are hidden with a `NoDisplay=true` copy in `/usr/local/share/applications`
  (delete the file to undo), never by editing the packaged file. No snaps. AppImages run
  with `libfuse2t64`; AppManager (module 04d) is the AppImage manager (Gear Lever stays retired). Zorin Appearance, Zorin Connect, Web Apps,
  Windows App Support and Neovim are removed (Appearance only switches Zorin layouts/themes,
  which our branding fixes; wallpapers are Settings > Background / `noc bg`; its
  `zorin-appearance-layouts-*` packages go with it, the zorin-menu/taskbar/desktop-icons
  extensions our Start button and dock hook are separate packages). Vim cannot be removed
  (zorin-os-minimal depends on vim-tiny): its launcher is hidden. `hermes desktop` writes its own
  launcher every run; the wrapper hides it and sets `desktop.manage_launcher_entry=false`.

- **Python GUI apps must pin `#!/usr/bin/python3`.** In a real session a mise-managed `python3`
  is first on PATH and has no PyGObject, so `#!/usr/bin/env python3` dies with `No module named
  'gi'` at autostart while working fine from an SSH shell (different PATH). `noctraos-welcome`
  and `noctraos-appearance` hit this; `noctraos-search` already execs `/usr/bin/python3`.
- **`retire_apt` judges each package alone and only by collateral removals.** Batching them let one
  false positive (`zorin-os-tour-video` matches the protected `zorin-os` prefix) block all of
  them, and counting the requested package itself as a hit is wrong. The opposite holds for a
  package apt cannot plan at all (`apt-get -s remove` fails, e.g. `libreoffice-style-colibre`
  would break `libreoffice-core`): packages in a set depend on each other, so the WHOLE set is
  kept (a warning, not an abort), otherwise a half-removed set would be left for the next run.
- **Local KVM test VM (ubuntubox):** `qemu-system-x86_64 -enable-kvm` with OVMF, user-mode
  networking (`hostfwd` 2222->22), `-usb -device usb-tablet`, a monitor socket for `sendkey` and
  `screendump`, and a **QMP socket for clicks**: HMP `mouse_move` is relative and a tablet ignores
  it, QMP `input-send-event` with `abs` axes (0..32767) works. Keep the disk on a Linux filesystem
  (/mnt/nvme1 or the 2 TB drive, both ext4 now), never NTFS. ISO builds run in a Docker container that builds
  straight into `<dir>/work` on the ext4 drive (no `--privileged`, scratch removed afterwards; ~3 min per ISO).
  `iso/build-local.sh` falls back to a loop-mounted `work.img` (privileged) only when the drive is not a Linux filesystem.

## Verification checklist for any change

1. `bash -n` + shellcheck (docker) clean on touched scripts.
2. Fresh-clone audit: clone from GitHub, confirm new files exist.
3. Deploy to a test VM (the local KVM VM, or VM 114 if it still exists), full installer run,
   confirm green + idempotent second run.
4. If menus/theme changed: reboot the VM and check the session visuals.
5. If ISO-relevant: rebuild ISO on the node, boot-test to the installer
   screen (live session gets DHCP = squashfs valid), then restore VM 114.
6. Push, then verify the remote SHA server-side.

## Release pipeline (2026-10-07)

A release is a tag: `git tag vX.Y.Z origin/main && git push gitlab vX.Y.Z` (docs/release-runbook.md, top section).
`.gitlab-ci.yml` runs `release-build` (iso/build-release.sh), `release-publish` (iso/publish-release.sh) and
`release-site` (scripts/release-site-pr.sh) on a project runner tagged `noctraos-release` that lives on the
workstation (`iso/setup-release-runner.sh`); the checks stay on the TrueNAS Docker runner, which is unprivileged,
has no spare RAM and cannot do KVM. Rules that keep it safe:

- The release runner is ref-protected and `v*` tags are protected: a branch or MR pipeline can never reach the
  workstation's Docker, KVM or `~/secrets`. Do not add `tags: [noctraos-release]` to a job that runs on branches.
- `build-release.sh` builds from GitHub `main` (the ISO build clones it and first boot fetches it) and refuses a tag
  that is not main's head or a VERSION that is not the tag. `RELEASE_REHEARSAL=1 REHEARSAL_BRANCH=<b>` builds a
  branch into `release/vX-rehearsal/`, which `publish-release.sh` will not publish.
- `publish-release.sh` never overwrites `releases/vX/` in the bucket and verifies through the PUBLIC hostname.
- The site is changed only by `scripts/update-site-release.py` (tested on copies of the real files; it raises on a
  page it does not recognise). If you restructure `site/download.html`, run `tests/test_update_site_release.py`.
- Do not edit a build script while a build is running: bash reads scripts incrementally.
- **Do not merge to GitHub `main` while a release build runs** (from the tag push to `release-build` success, about
  90 minutes): the VM's first boot fetches `main` and the build fails if that is not the tagged commit.
- First real run (v0.3.2) found three things, all fixed: GitLab's shell executor starts a login shell and Ubuntu's
  `~/.bash_logout` runs `clear_console` at SHLVL 1, so the runner unit sets `SHLVL=2` ("prepare environment: exit
  status 1"); a 17 GB stream through the CDN can drop (curl 92), so verification downloads with resume; R2 answers
  an occasional 501 to a copy that succeeds on rclone's retry (harmless). A failed `release-publish` is safe to
  retry: it hashes what is already in the bucket and uploads only what is missing.

## Control Panel (built 2026-10-06, PRs #40 to #48)

The zenity `noc-menu` is gone; `noctraos-control` is the GUI for `noc` (docs/control-panel.md). Pages:
Overview, Updates, AI models, Hardware, Health, Privacy, About. Root work goes through
`noc-privileged` only. Merge the stacked PRs in order and release them together: between the phases
update and GPU setup had no GUI.

## Current state (2026-10-08)

Version **0.4.0** (`VERSION`), released by the pipeline on 2026-10-08: tag `v0.4.0` (f377828, GitLab pipeline 122: `release-build`
37 min, `release-publish` 35 min, `release-site` 1 min), files at `https://dl.noctraos.dev/releases/v0.4.0/` (ISO 3.9 GB, QCOW2 17 GB,
VMDK 17 GB, SHA256SUMS, each verified through the public hostname), GitHub release, site and torrent updated by `release-site`
(PR #70). `v0.3.2`, `v0.3.1` and `v0.3.0` stay published. The text below describes 0.3.1 and the 0.3.0-era runbook; the steps and
scripts are the same for any version, and `docs/release-runbook.md` (top section) is the pipeline procedure.

What 0.4.0 added: the Accounts page (Git name/e-mail and the GitHub sign-in with no terminal), the Apps page and `noc-upstream`
(installed vs newest release of Hermes, Ollama, AppManager and the coding agents), the built-in updater `noc-selfupdate`
(signed, staged updates of the NoctraOS layer, `docs/updates.md`), and the fastest-disk policy for VM disks and ISO scratch
(`iso/disks.sh`). Still untested: a full interactive ISO install, real hardware, NVIDIA/ROCm, a real desktop session running the
GitHub approval and the privileged update prompts, and a machine applying an update from a real desktop. Not in the Control Panel
yet: signing in to the coding agents.

**Update channels (2026-10-08):** `nightly` and `stable` are both at update 2 (update 1 was a baseline identical to 0.4.0; update 2
is the client fix below). Manifests expire after 30 days; the weekly timer from `iso/setup-update-renewal.sh` renews both
(`status` shows the real expiry). The 0.4.0 images contain the pre-fix client and receive the fix as update 2.

What the first 0.4.0 run taught us, all fixed:
- **GitLab runs the tests as root in a container; a normal-user run on the workstation does not prove the CI will pass.** `noc`
  ignores `NOC_SELFUPDATE`/`NOC_UPSTREAM`/`NOC_ACCOUNTS` as root (so the privileged helper and `sudo noc update` always use the
  installed copies) and nine tests failed on `main` (pipeline 120). Tests now set `NOC_TEST_HOOKS=1`. Before tagging: run the
  whole suite as root in a container with a real clone, and push `main` to GitLab and wait for green. Mounting a worktree into the
  container breaks git (the `.git` file points outside it); use `git clone --no-hardlinks` into a directory you mount.
- **S3-style storage answers 403, not 404, for a key that does not exist** (the Hetzner mirror). The update client now treats a 403
  for the manifest as "nothing published yet", and one answering mirror is enough when another is unreachable.
- **Rehearse the final `main`, not an earlier one.** A rehearsal of the commit before the last merges proves nothing about the tag;
  `RELEASE_REHEARSAL=1 REHEARSAL_BRANCH=main iso/build-release.sh <dir>` takes about 42 minutes and publishes nothing. Do not merge
  while it runs (stop it first if the merges supersede it).
- **Stacked PRs: retarget each to `main` before merging it.** Merging a PR into a branch that was already merged never reaches `main`.
- **`gh pr edit` fails on this repository** (GitHub's classic-projects deprecation error): use `gh api -X PATCH repos/OWNER/REPO/pulls/N -F body=@file`.
- A background job started from a tool call is killed at about 10 minutes: run anything longer (a rehearsal, an offload) as a
  `systemd-run --user` unit and watch its log. Never `pkill -f <pattern>` when your own command line contains the pattern.

- On `main`: provisioner modules 00 to 11 (Hermes Desktop last), the app policy
  (`04c_app_policy.sh`: Flatpak/AppImage first, unwanted apps removed, launchers hidden), the
  NoctraOS welcome (replaces Zorin's tour), the Control Panel and its root helper (see the Control Panel
  section above), the appearance panel, the release/unattended ISO split, `iso/build-local.sh`,
  `iso/local-vm.sh`, `iso/vm-sysprep.sh`, and the `nightly` staging workflow (`docs/nightly.md`).
- Published (2026-10-06): the release ISO, the QCOW2 and VMDK VM disks and `SHA256SUMS` at
  `https://dl.noctraos.dev/releases/v0.3.1/` (the same R2 bucket as files.dazeb.dev; each file's SHA-256 was
  checked by streaming it back through the public hostname). Built from `main` at 95c5097 with
  `iso/build-local.sh <dir> both`; first boot clones `main`. The ISO torrent in the repo root
  (`noctraos-0.3.1-amd64.iso.torrent`, web seed on dl.noctraos.dev) is for this ISO: rebuild it whenever the
  ISO changes (torf in a throwaway venv; same trackers, 4 MiB pieces). `v0.3.0` stays published beside it.
- Released: tag `v0.3.1` (the release merge commit: it adds the torrent and the download page to the
  `main` the ISO was built from, 95c5097) and the GitHub release with links and checksums
  only (GitHub caps assets at 2 GiB). Do not move the tag; later fixes go in the next version. Known
  issues shipped in 0.3.1, fixed on main afterwards (they ship in the next release): the card tooltip read
  "Open Ai Models"; Super+Space and the Start panel needed one sign-out/in on the first login (extensions installed
  by the first-boot provisioner are not seen by the running shell; now baked into the ISO, `iso/bake-shell.sh`);
  windows had a dark wedge in the top-left corner (see the pitfall on per-corner radii).
- Never published: the unattended/appliance ISO. The old unattended test ISO that was public at
  the bucket root was deleted.
- Tested: `proxmox-install.sh` against the public files on a PVE 9.2 node, both modes (the image boots to the
  welcome; the ISO boots to the installer); the release ISO boots to the installer; the appliance ISO installs and provisions
  unattended end to end; both exported VM disks (QCOW2, VMDK) boot, autologin into the welcome,
  bring up SSH on their own with a new host key, and pass `noc doctor`.
- Untested: the welcome while first-boot provisioning is still running, a full interactive
  install of the release ISO, and real hardware. See the runbook.
- Old reference VMs: VM 114 (192.168.8.187, v0.2) and VM 110 `zai-zerotouch-test` may be stale or
  gone; the local KVM VM (`iso/local-vm.sh`) is the fast test bed now.
- Renamed from `zorin-ai` to **NoctraOS** (slug `noctraos`), the CLI `zom` to `noc`: clean breaks,
  no migration shims. Zorin OS remains the upstream base and is named only as such.
- Roadmap ideas: prefilled search examples in the welcome (D-Bus `Open(query)`), a provisioner
  log panel, Aider/Goose launchers, greeter-bug root cause, an AppImage build of Hermes Desktop
  hosted on files.dazeb.dev to replace the 25 to 40 minute first-boot Electron build.
  From an outside suggestion list, checked against primary sources 2026-10-07. Done: `noc doctor` row
  `flatpak-security` (Flatpak 1.18.4, 2026-09-28, fixed six CVEs, two of them root file overwrite/delete; Ubuntu
  24.04 listed CVE-2026-97024 as "needs evaluation", so the row passes on version >= 1.18.4 OR the CVE named in
  the package changelog, `NOC_FLATPAK_CHANGELOG` overrides the path in tests), and `capabilities` per model in
  `noc models list --json`, shown in the Control Panel's installed list. Not done, needs design first:
  push-to-talk dictation for Super+Space (Qwen3.8-Omni-Flash exists but only as a paid API, so wait for open
  weights); a "pause and ask" step before an agent sends files off the device or installs something;
  folder-scoped, revocable agent permissions plus a log of what left the device (PixelLeak, 2026-09-29:
  coding agents pushed 13,000+ internal screenshots to public GitHub repos); the upgrade path from Zorin 18's
  Ubuntu 24.04 base to the next LTS; shipping a newer Flatpak in the ISO if Ubuntu is slow to patch.
  Rejected: bumping agent versions (agents install unpinned from npm, nothing is pinned), per-model disk cost
  and removal (already in the AI models page), content search (already in Super+Space). Not confirmed by any
  source: Ollama v0.35.1 (0.35.0 is the newest seen), a Windows 26H2 AI comparison, and a RemoveMacAI
  "backlash" (the tool is real: macOS 27, about 12 GB of models).
