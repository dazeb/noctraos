# Developing NoctraOS (contributors and agents in the repo)

Read the repo `AGENTS.md` first; it is authoritative and longer than this page. The workspace and `projects/` `AGENTS.md` files apply too.

## Repository map (short)

```
install.sh, boot.sh, proxmox-install.sh   orchestrator, remote fetcher, Proxmox VM installer
install/        modules 00-11 (+01b, optional/), lib.sh helpers
bin/            noc, noc-gpu, noc-disk, noc-accounts, noc-upstream, noc-selfupdate, noc-privileged, noctraos-* programs
control/        Control Panel (panel.py pure, main.py/pages.py GTK)
search/, extensions/, branding/, help/      Super+Space, GNOME Shell extensions, layout script, help page
configs/        seeded configs (mise, vscode, copyq, theme, systemd, polkit, update, hermes, applications, autostart, agent-skills ...)
assets/         wallpapers, icons, boot artwork
scripts/        render-theme.py, build-desktop-theme.py, seed-password-store.py, make-update.py, site/release helpers
migrations/     system/ and user/ scripts run once on update
iso/            ISO remaster, release/update publishing, local VM, runner setup
site/           static project website (deployed by Cloudflare when GitHub main updates)
docs/           objectives (source of truth), what-we-do, flavours, updates, control-panel, theme-design, release-runbook, ...
tests/          unittest suite (theme, GPU, noc JSON, root helper, panel, installer, update pipeline, site)
.agents/skills, skills-lock.json   vendored pstack agent skills - not product code
```

## Non-negotiable rules

1. **Never run `install.sh`/`boot.sh` on the dev workstation** (`dazeb-ubuntubox`, Ubuntu 26.04). It is for editing and static checks. Runtime testing happens in a test VM (`iso/local-vm.sh` local KVM, the fast bed, or the Proxmox VM).
2. **Every module is idempotent.** Re-running install.sh must be a no-op.
3. **Desktop settings are warn-not-die**; core steps (apt, ollama) may die.
4. No bare `gs`; no `grep -q` on big pipes under pipefail; gsettings through `as_user` on the user bus.
5. **Verify pushes server-side**: `gh api repos/dazeb/noctraos/commits/heads/main --jq .sha`. A clean `git push` exit code has lied once.
6. **Commit on `main`** (or an intentional branch). If `git status` shows a feature branch you did not create, stop and reconcile.
7. Do not touch other guests on the Proxmox node (VMs 107/108/113/114 are others' except 114 `zorin-ai-iso-test`, which is ours; LXC 100-112/200/210).
8. **Flavours are not forks.** Name the flavour in commits, PRs and reports; never copy a fix between flavours.
9. Keep secrets in `~/secrets` / `.env`; never commit datasets, weights, credentials or build output; do not commit `.codex/`.

## Checks

```bash
bash -n boot.sh install.sh install/*.sh install/optional/*.sh bin/noc bin/noc-gpu bin/noc-privileged bin/noctraos-control \
  bin/noctraos-agent bin/noctraos-copyq bin/noctraos-hermes bin/noctraos-search configs/nautilus-scripts/*
docker run --rm -v "$PWD:/mnt" koalaman/shellcheck:stable --severity=warning <same list>   # same as CI
python3 -m unittest discover -s tests          # the suite (639 tests at last count; AGENTS.md carries the number)
python3 scripts/render-theme.py --check        # committed theme outputs match palette.json
```

Also: `VERSION` must match `bin/noc` and `bin/noc-gpu`. CI is GitLab (`.gitlab-ci.yml`, homelab, project `dazeb/noctraos`) - GitHub Actions does not run on this account. Run the suite as root in a container before a release (some tests differ).

## Adding things - checklists

- **A `noc` command / panel action:** logic in `bin/noc` first, panel calls it, add to `TERMINAL` and `docs/control-panel.md`; keep `--json` keys stable; extend `tests/test_noc_cli.py`.
- **A root action:** a fixed verb in `bin/noc-privileged` (no caller-supplied path/URL/command/package); a module only if idempotent and safe unattended -> `MODULES` + `tests/test_noc_privileged.py`.
- **A setup chore:** `SKIPPABLE` in both places, skip button + skipped state, `TERMINAL` entry, `setup_steps()` step + test, Welcome app text if it shows commands.
- **A change for installed machines:** update item lists in sync (three places), write an idempotent additive migration (modules 06/08/09 are not re-run by updates), publish the next serial. Optional: `docs/what-we-do.md` if a default changes.
- **New project folder** names are lowercase kebab-case; reusable material goes in `shared/`.

## Test infrastructure

- Local KVM test VM: `iso/local-vm.sh` (start/stop, console screenshot, absolute clicks via QMP `input-send-event`, keys, ssh/scp; no root, no host changes). OVMF, user-mode networking (`hostfwd` 2222->22), keep the disk on ext4 (never NTFS).
- Proxmox node `ssh root@192.168.8.195`; test VMs 110 (`zai-zerotouch-test`, 192.168.8.138) and 114 (`zorin-ai-iso-test`, 192.168.8.187, v0.2); user `dazeb`, throwaway password in `AGENTS.md`. Node has about 4 GiB free RAM: one 3 GiB VM at a time, and not while ISO builds run there.
- Remote from a cloud agent: Tailscale userspace mode, tailnet IPs (VM 114 `100.125.207.0`, node `100.83.252.94`); auth keys are pasted by the user per session, never committed, revoked afterwards.
- AMD GPU VM on TrueNAS (`192.168.8.111`, VM id 1; `midclt call vm.start|vm.stop 1`): RX 580 passthrough, Vulkan verified; stop it when done (8 GiB).
- Driving a VM desktop: unlock the session over SSH (`gdbus ... org.gnome.ScreenSaver.SetActive false`), `gnome-screenshot -f`, keys via `/dev/uinput` (sudo). Prefer SSH over VNC typing (VNC drops shifted characters). Never `pkill -f <pattern>` in an ssh one-liner.
- Boot screens without the node: stage boot pieces with `iso/boot-theme.sh` into a copy of the Zorin ISO, boot under `qemu-system-x86_64` and take `screendump`s; Plymouth previews with `plymouthd --no-daemon` under Xvfb.

## Deploy a change to a test VM (idempotent full pass)

```bash
tar czf /tmp/noctraos-repo.tgz --exclude=.git --exclude=.zcodeignore .
scp -q /tmp/noctraos-repo.tgz dazeb@<vm>:/tmp/
ssh dazeb@<vm> 'rm -rf ~/.local/share/noctraos && mkdir -p ~/.local/share/noctraos \
  && tar xzf /tmp/noctraos-repo.tgz -C ~/.local/share/noctraos \
  && nohup bash ~/.local/share/noctraos/install.sh > /tmp/noctraos-run.log 2>&1 &'
```

Verification checklist: static checks clean -> fresh-clone audit (`git clone` and confirm new files exist) -> deploy, full run, **second run is a no-op** -> reboot and look if menus/theme changed -> ISO rebuild and boot test if ISO-relevant -> push and verify the remote SHA.

## What is untested (say so in reports)

A full interactive ISO install, real hardware, NVIDIA/ROCm, VMware/VirtualBox/Hyper-V guest paths, a real desktop session running the GitHub approval and privileged update prompts, the `copyq eval` clear script, and the `ssh.socket` switch. The kubuntu flavour has no release.

## Installing this skill

This skill lives at `configs/agent-skills/noctraos/` and is installed by `bin/noc-agent-skills` (`noc agent-skills install|status|remove|on`) into `~/.agents/skills/noctraos`, the global agents folder. Codex reads `~/.agents/skills` directly; Hermes and Claude Code get a relative symlink (`~/.hermes/skills/noctraos`, `~/.claude/skills/noctraos` -> `../../.agents/skills/noctraos`) when those agents are present. No agent setting is written. Module 07 runs it on every install and update (from the root-owned snapshot), module 11 runs it again once Hermes exists, and `migrations/user/0002_install_agent_skill.sh` catches up other accounts. It never overwrites a folder it did not install or one the person edited, and `~/.config/noctraos/no-agent-skills` (made by `remove`) switches it off. Tests: `tests/test_agent_skills.py` (also checks this skill's frontmatter and that every reference is linked).

Keep the skill in step with the code: when a command, rule or default changes, update the matching reference file in the same change. Keep SKILL.md small and put detail in `references/`. Frontmatter is only `name` (equal to the folder) and `description` (under 1024 characters) so Hermes, Codex and Claude Code all accept it.
