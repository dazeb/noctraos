# Omarchy application and theme comparison

Compared against [Omarchy's current core package manifest](https://github.com/basecamp/omarchy/blob/quattro/install/omarchy-base.packages) at commit `8b4eae66da2938ba9559f103b18dbf85cdf28a70` (checked 2026-09-30). This is functional parity for a Zorin/GNOME workstation, not a copy of Arch, Hyprland, or Omarchy's branding.

| Omarchy area | NoctraOS implementation |
| --- | --- |
| Browser and notes | Chromium and Obsidian from Flathub; Zorin's existing browser remains available |
| Office and documents | LibreOffice, Evince, Xournal++ from Ubuntu |
| Media and creation | MPV, Kdenlive, OBS Studio, Flameshot, and gThumb from Ubuntu; Pinta and Moonlight from Flathub |
| Files and sharing | Nautilus, GNOME Sushi preview, GNOME Disks, CUPS printing, and Tesseract OCR from Ubuntu; LocalSend from Flathub |
| Terminal and developer tools | btop, bat, eza, fd-find, fzf, ripgrep, zoxide, neovim, tmux, ffmpeg, ImageMagick, yt-dlp, tldr, clang, Ruby, GitHub CLI, Docker with Compose, and common storage/network utilities from Ubuntu; Starship, lazygit, and lazydocker from mise |
| Agent sessions | [Herdr](https://herdr.dev/docs/install/) from mise, with a Development menu launcher and NoctraOS palette |
| Local AI | Ollama, Microsoft VS Code/Continue, six agent launchers, and model manager already provisioned by NoctraOS |
| Desktop appearance | NoctraOS-Dark GNOME Shell and GTK (derived from installed Zorin themes), polygon wallpapers, white menu glyphs, shared Omarchy-inspired Matte Black colors for GNOME Terminal, VS Code, Herdr, and btop |

The installer checks the Ubuntu archive before installing each package and logs any missing package. Flathub installs are independently guarded and log failures. `zom doctor` reports the core AI stack plus Herdr and Starship.

Omarchy's Hyprland compositor, SDDM greeter, Arch package manager, hardware-specific packages, and Omarchy-only applications (`aether`, `omacalc`, `omasnap`, `omawrite`, `owe`) do not map directly to Zorin. Zorin's GNOME desktop supplies the corresponding desktop workflows. Omarchy's service web shortcuts and its theme switcher are not provisioned here; the NoctraOS theme is currently one coordinated fixed palette.

Validation: run `bash -n` and ShellCheck locally. Then run the installer twice on VM 114, verify the package and Flatpak IDs, Herdr launch, and the GNOME Terminal, VS Code, Herdr, and btop colors. Reboot for shell/menu visuals. An ISO rebuild is required before these changes appear in the bootable image.

## App refresh shortlist — 2026-09-30

Chatbox, VSCodium, and Foot are excluded. The GUI installer installs Microsoft
VS Code through its signed stable apt repository before removing the old apt
packages. Settings and chat data are retained; GNOME Terminal remains available.

The following are candidates, not new default installs:

| Candidate | Use | Integration work |
| --- | --- | --- |
| [Fastfetch](https://github.com/fastfetch-cli/fastfetch) | System information and workstation branding | Upstream Debian package; verify on Ubuntu 24.04 |
| [Gum](https://github.com/charmbracelet/gum) | Interactive terminal menus | Official Charm apt repository; useful when improving zom |
| [dua](https://github.com/Byron/dua-cli) | Interactive disk usage | Upstream Linux binary; overlaps existing ncdu |
| [CLIamp](https://github.com/bjarneo/cliamp) | Terminal music player | Upstream Linux installer; validate audio bridge on Zorin |
| [Hype](https://github.com/omacom/hype) | Markdown presentations | Ubuntu packaging and Omarchy-theme adaptation needed |
| [Monologue](https://github.com/omacom/monologue) | Webcam recording and trimming | Ubuntu packaging and Omarchy-theme adaptation needed |
| [Omacut](https://github.com/omacom/omacut) | Video trimming | Qt 6 source build, Ubuntu packaging, and theme adaptation needed |

For the AI workstation rather than Omarchy parity, [Aider](https://aider.chat/docs/install.html)
and [Goose](https://github.com/aaif-goose/goose) are additional launcher candidates.
They need non-npm installation paths and provider configuration.
