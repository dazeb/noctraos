# Privacy and accounts

## Privacy page / `noc privacy`

`noc privacy status [--json]` is the single implementation (the page only words it). Three things the installer arranges without asking are *settings, not setup chores*: no skip button, no Overview nag.

| Item | State / action |
|---|---|
| **Hermes mode** | `noc privacy hermes status\|local\|cloud`. The Nous free tier is a cloud service and the page must never say otherwise; switching to cloud needs an explicit confirmation; a user's own provider (`mode: other`) is left alone. `local` = `noctraos-hermes local --no-launch`. |
| **Remote login** | `openssh-server` comes from module 01. On Ubuntu 24.04 sshd starts from `ssh.socket`, so state is "on" when the socket or the service is active/enabled; `remote off` (via `noc-privileged remote-access off`) disables **both** (disabling only `ssh.service` leaves the socket listening). `remote on` re-enables the socket (else the service) and confirms first. |
| **Clipboard history** | CopyQ keeps it on disk. `clipboard clear` counts and clears only the default `&clipboard` tab through fixed `copyq eval` scripts run as the X11 client (nothing from the clipboard or person is put into them) and asks CopyQ only while it runs (asking would start it). |
| **Saved passwords** | See below. The page only states the trade-off and offers Passwords and Keys; it never changes the keyring. |

Tests stand in for `systemctl`, `copyq` and the keyring file with `NOC_KEYRING_FILE` and PATH stubs; `noc privacy remote` reaches `noc-privileged` through `sudo` (`NOC_PRIVILEGED` in tests). Untested on a real desktop: the `copyq eval` clear script and the `ssh.socket` switch.

## The unlocked login keyring (autologin trade-off)

Autologin leaves the login keyring locked, so apps using the Secret Service (Hermes Desktop, browsers, VS Code) would show "Authentication required". `scripts/seed-password-store.py` (modules 04 and 07) replaces the user's login keyring with an **unencrypted** one (`~/.local/share/keyrings/login.keyring` + `default`) when it is missing or empty (about 105 bytes), then module 04 restarts `gnome-keyring-daemon`. A keyring that holds secrets, or one in an unrecognised format, is **never touched**. It also adds `--password-store=basic` for Chromium (Flatpak) and `"password-store": "basic"` for VS Code, so a keyring password would not cover them. Accepted trade-off: secrets are stored without a password. Existing keyrings that hold secrets keep prompting on autologin.

## Git and GitHub (Accounts page / `noc accounts`)

For people who are not developers: never make this need a terminal, a token or a command to copy.

- `noc accounts git set --name N --email E` writes `git config --global`.
- `noc accounts github login` runs `gh auth login --web` with prompts off (stdin closed, `GH_PROMPT_DISABLED=1`; prints a one-time code and URL then waits, no Enter), strips `GH_TOKEN`/`GITHUB_TOKEN` from the environment (gh refuses to log in while they are set), runs `gh auth setup-git` so `git push` works, and `suggest` offers GitHub's private `ID+login@users.noreply.github.com` address (pushes that would reveal a private address are rejected). `logout` signs out.
- It never reads or prints a token. Local status reads `~/.config/gh/hosts.yml`; `--verify` asks GitHub. The sign-in subprocess is stopped with SIGTERM (Cancel); its timer thread must stay a daemon or the program will not exit.
- Skippable: `noc skip add git|github`. After that nothing nags.

## Skipping chores (`noc skip`)

`~/.config/noctraos/skipped`, one id per line; `noc status --json` carries it as `skipped`. A chore already done is never shown as skipped. Commands appear only where the person declined a chore or asked for them.

## Principle for agents

Anything that sends data off the machine, costs memory, or belongs to the person is an opt-in with a `noc` twin, never a default you silently choose. Say it in plain words; `docs/what-we-do.md` is the user-facing statement and must stay current when a default changes.
