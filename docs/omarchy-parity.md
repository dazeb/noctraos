# Omarchy application and theme comparison

Compared against [Omarchy's current core package manifest](https://github.com/basecamp/omarchy/blob/quattro/install/omarchy-base.packages) at commit `8b4eae66da2938ba9559f103b18dbf85cdf28a70` (checked 2026-09-30). This is functional parity for a Zorin/GNOME workstation, not a copy of Arch, Hyprland, or Omarchy's branding.

| Omarchy area | NoctraOS implementation |
| --- | --- |
| Browser and notes | Chromium and Obsidian from Flathub. Zorin's Brave is removed so there is one browser |
| Office and documents | LibreOffice, Evince and Xournal++ from Flathub |
| Media and creation | VLC, MPV, Kdenlive, OBS Studio, Flameshot, gThumb, Pinta and Moonlight from Flathub |
| Files and sharing | Nautilus, GNOME Sushi preview, GNOME Disks, CUPS printing, and Tesseract OCR from Ubuntu; LocalSend from Flathub |
| Application policy | Flatpak and AppImage first, apt for CLI and system tools (`install/04c_app_policy.sh`); [AppManager](https://github.com/kem-a/AppManager) installs and updates AppImages; the apt copy of an app is retired once its Flatpak is in |
| Terminal and developer tools | btop, bat, eza, fd-find, fzf, ripgrep, zoxide, tmux, ffmpeg, ImageMagick, yt-dlp, tldr, GitHub CLI, Docker with Compose, and common storage/network utilities from Ubuntu; Starship, lazygit, and lazydocker from mise. No Ruby, clang, Python or Go: nothing in NoctraOS needs them (Node.js comes from mise because the agents and Hermes do), and people add their own languages with mise |
| Agent sessions | [Herdr](https://herdr.dev/docs/install/) from mise, with a Development menu launcher and NoctraOS palette |
| Local AI | Ollama, Microsoft VS Code/Continue, the Hermes Desktop app plus six CLI agent launchers (Codex, Claude Code, OpenCode, Grok, Gemini CLI, Qwen Code), and a model manager, all provisioned by NoctraOS. Hermes' free tier is a cloud service, unlike the local model |
| Launcher and search | Super+Space overlay (apps, files, clipboard history, web, opt-in browser history) as the system launcher, where Omarchy uses its own app launcher |
| Desktop appearance | NoctraOS-Dark GNOME Shell and GTK (derived from installed Zorin themes), polygon wallpapers, white menu glyphs, shared Omarchy-inspired Matte Black colors for GNOME Terminal, VS Code, Herdr, and btop |

The installer checks the Ubuntu archive before installing each package and logs any missing package. Flathub installs are independently guarded and log failures. `noc doctor` reports the core AI stack plus Herdr and Starship.

Omarchy's Hyprland compositor, SDDM greeter, Arch package manager, hardware-specific packages, and Omarchy-only applications (`aether`, `omacalc`, `omasnap`, `omawrite`, `owe`) do not map directly to Zorin. Zorin's GNOME desktop supplies the corresponding desktop workflows. Omarchy's service web shortcuts and its theme switcher are not provisioned here; the NoctraOS theme is one coordinated fixed palette, and `noctraos-appearance` only changes the wallpaper and fonts. Neovim is not shipped (Omarchy's is); Vim stays installed because Zorin depends on it, with its launcher hidden.

Validation: run `bash -n` and ShellCheck locally. Then run the installer twice on a test VM (the local KVM VM from `iso/local-vm.sh`, or VM 114), verify the package and Flatpak IDs, Herdr launch, and the GNOME Terminal, VS Code, Herdr, and btop colors. Reboot for shell/menu visuals. An ISO rebuild is required before these changes appear in the bootable image.

## App refresh shortlist — 2026-09-30

Chatbox, VSCodium, and Foot are excluded. The GUI installer installs Microsoft
VS Code through its signed stable apt repository before removing the old apt
packages. Settings and chat data are retained; GNOME Terminal remains available.

The following are candidates, not new default installs:

| Candidate | Use | Integration work |
| --- | --- | --- |
| [Fastfetch](https://github.com/fastfetch-cli/fastfetch) | System information and workstation branding | Upstream Debian package; verify on Ubuntu 24.04 |
| [Gum](https://github.com/charmbracelet/gum) | Interactive terminal menus | Official Charm apt repository; useful when improving noc |
| [dua](https://github.com/Byron/dua-cli) | Interactive disk usage | Upstream Linux binary; overlaps existing ncdu |
| [CLIamp](https://github.com/bjarneo/cliamp) | Terminal music player | Upstream Linux installer; validate audio bridge on Zorin |
| [Hype](https://github.com/omacom/hype) | Markdown presentations | Ubuntu packaging and Omarchy-theme adaptation needed |
| [Monologue](https://github.com/omacom/monologue) | Webcam recording and trimming | Ubuntu packaging and Omarchy-theme adaptation needed |
| [Omacut](https://github.com/omacom/omacut) | Video trimming | Qt 6 source build, Ubuntu packaging, and theme adaptation needed |

For the AI workstation rather than Omarchy parity, [Aider](https://aider.chat/docs/install.html)
and [Goose](https://github.com/aaif-goose/goose) are additional launcher candidates.
They need non-npm installation paths and provider configuration.
