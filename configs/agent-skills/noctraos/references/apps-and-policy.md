# Apps and the app policy

## Flatpak and AppImage first

`install/04_workstation_apps.sh` lists the Flatpaks (the Omarchy-style workstation set plus apt CLI/system tools); `install/04c_app_policy.sh` enforces the rest. **apt is for CLI tools, system tools and host-integration apps** (VS Code, CopyQ, Docker). **No snaps.**

- Once an app's Flatpak is in, the apt copy is retired. Retirements simulate `apt-get -s remove` first and skip if apt would also remove a protected package (`zorin-os*`, `gnome-shell`, ...). `retire_apt` judges each package alone and only by collateral removals; for a package apt cannot plan at all, the **whole set** is kept (a warning, not an abort) so a half-removed set is never left.
- Launchers are hidden with a `NoDisplay=true` copy in `/usr/local/share/applications` (delete that file to undo), never by editing the packaged file.
- Removed on purpose: Zorin Appearance (and its `zorin-appearance-layouts-*`), Zorin Connect, Web Apps, Windows App Support, Neovim, plus VSCodium/Chatbox/Foot (user data kept; `apt-get remove`, never purge/autoremove). Vim cannot be removed (`zorin-os-minimal` depends on `vim-tiny`), so its launcher is hidden.
- Flatpak/AppImage prerequisites (`install/01_system.sh`) are identical on every flavour: FUSE 2 and 3 plus all four desktop portal backends. On Zorin the KDE portal backend adds 74 packages / about 95 MiB (measured 2026-10-10); GNOME still routes to its own backends and the Secret portal stays pinned to gnome-keyring.
- AppImages run with `libfuse2t64`; **AppManager** (kem-a/AppManager, module `04d_appmanager.sh`, sha256-verified release in `/opt/appmanager`, non-fatal, rerun with `install.sh --only 04d_appmanager.sh`) is the AppImage manager. Gear Lever stays retired.
- `noc doctor` has a `flatpak-security` row: passes on Flatpak >= 1.18.4 or when the CVE is named in the package changelog (`NOC_FLATPAK_CHANGELOG` overrides the path in tests).

## VS Code

Microsoft `code` from the apt repo (key `/usr/share/keyrings/microsoft.gpg`, source from `configs/vscode/vscode.sources`; `debconf-set-selections` stops the package adding its own repo). Settings, `extensions.list` and the Continue config (`continue_config.yaml`) are **seeded only when missing**, so existing installs keep theirs; they follow the default model file ([local-ai](local-ai.md)). `--password-store=basic` is set (see [privacy-and-accounts](privacy-and-accounts.md)). No Go extension; install only what NoctraOS itself needs.

## Languages and tools (mise)

Node LTS is the **only** language: the agent launchers' npm and the Hermes build use it. `configs/mise/config.toml`: `node=lts` plus terminal tools (no Python/Go). `02_mise.sh` installs the mise binary, `profile.d` + `bash.bashrc` hooks, Herdr, Starship, lazygit, lazydocker. People add languages with `mise use -g`. Existing machines keep whatever they have; nothing is removed behind anyone's back. `noc doctor` shows Python and Go as `info` when absent, never `fail`.

## Install only what NoctraOS needs

Rule from the owner: if a language or heavy component does not need to be in the OS, it is not. No local model downloads by default. The app set itself is a deliberate, specific selection: keep it. New installs only.
