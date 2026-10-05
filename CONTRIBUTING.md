# Contributing to NoctraOS

Welcome. You can help whether you're new to Linux, learning to code, or have
been building desktops for years. Small improvements are welcome; you don't
need a big feature or a perfect proposal.

## Find a way in

- **Try it.** Tell us what worked, what confused you, and what your hardware is.
- **Explain it.** Fix a typo, improve a guide, or help make first-run instructions clearer.
- **Make it look better.** Share screenshots, accessibility feedback, or design ideas.
- **Build it.** Fix a bug, improve search, or help with themes, apps, and setup.

[Open an issue](https://github.com/dazeb/noctraos/issues) if you're unsure where
to start. Say what interests you and how much experience you have; we'll work
out a useful first step together. No Linux wizard hat required.

## Report a bug or suggest an idea

For a bug, include what you expected, what happened, and how to reproduce it.
Add the NoctraOS version and relevant hardware. Screenshots and the relevant
part of a log are helpful; remove passwords, tokens, and personal information.
You can run `noc doctor` inside NoctraOS to check the setup.

For an idea, tell us what it would help you do. For a larger change, start with
an issue so we can agree on the direction before you spend a weekend on it.

## Send a change

1. Fork the repository and make a branch for your change.
2. Read [the objectives](docs/objectives.md) and the relevant guide below.
   For installer, desktop, or ISO changes, also read [AGENTS.md](AGENTS.md)
   for the project rules and known pitfalls.
3. Make a focused change. If behaviour changes, update the matching docs.
4. Check the parts you changed, then open a pull request describing what
   changed, why, and how you checked it.

It's fine to open a draft PR or ask for help when you're stuck. Documentation
and screenshot contributions don't need an OS rebuild.

## Where things live

| Area | Starting points |
| --- | --- |
| Setup and app installation | `install/`, `bin/`, [setup guide](docs/setup.md) |
| Search, Start panel, and welcome | `search/`, `extensions/`, [onboarding](docs/onboarding.md), [desktop layout](docs/desktop-layout.md) |
| Colours, icons, and wallpapers | `configs/theme/`, `assets/`, [theme design](docs/theme-design.md) |
| Website and documentation | `site/`, `docs/` |
| ISO builds and VM testing | `iso/`, [release runbook](docs/release-runbook.md) |

## Check your work

For Python, GPU detection, or theme changes, run the existing checks from the
repository root (GPU detection tests use fixtures; they don't install drivers):

```bash
python3 -B -m unittest discover -s tests -v
python3 -B scripts/render-theme.py --check
```

For shell changes, run `bash -n` and ShellCheck on the changed scripts. The
[GitLab CI configuration](.gitlab-ci.yml) lists the full checks.
For documentation or images, check the links and how they render on GitHub.

**Run the installer only in a disposable VM, never on your development
machine.** It changes packages, drivers, and desktop settings. Keep installer
modules safe to rerun, and verify runtime changes in a VM; the
[setup guide](docs/setup.md#testing-and-vm-images) covers the available tooling.

Be kind, give useful feedback, and leave room for people to learn. That's how
we want this project to feel.
