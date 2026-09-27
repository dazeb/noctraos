# Omarchy application and theme comparison

Compared against [Omarchy's current core package manifest](https://github.com/basecamp/omarchy/blob/quattro/install/omarchy-base.packages) at commit `0066ea2` (2026-09-27). This is functional parity for a Zorin/GNOME workstation, not a copy of Arch, Hyprland, or Omarchy's branding.

| Omarchy area | Zorin AI implementation |
| --- | --- |
| Browser and notes | Chromium and Obsidian from Flathub; Zorin's existing browser remains available |
| Office and documents | LibreOffice, Evince, Xournal++ from Ubuntu |
| Media and creation | MPV, Kdenlive, OBS Studio, Flameshot, and gThumb from Ubuntu; Pinta and Moonlight from Flathub |
| Files and sharing | Nautilus, GNOME Sushi preview, GNOME Disks, CUPS printing, and Tesseract OCR from Ubuntu; LocalSend from Flathub |
| Terminal and developer tools | btop, bat, eza, fd-find, fzf, ripgrep, zoxide, neovim, tmux, ffmpeg, ImageMagick, yt-dlp, tldr, clang, Ruby, GitHub CLI, Docker with Compose, and common storage/network utilities from Ubuntu; Starship, lazygit, and lazydocker from mise |
| Agent sessions | [Herdr](https://herdr.dev/docs/install/) from mise, with a Development menu launcher and Zorin AI palette |
| Local AI | Ollama, Chatbox, VSCodium/Continue, six agent launchers, and model manager already provisioned by Zorin AI |
| Desktop appearance | ZorinAI-Dark GNOME Shell and GTK (derived from installed Zorin themes), neon wallpaper, white menu glyphs, GNOME Terminal palette, VSCodium colors, Herdr colors, btop theme |

The installer checks the Ubuntu archive before installing each package and logs any missing package. Flathub installs are independently guarded and log failures. `zom doctor` reports the core AI stack plus Herdr and Starship.

Omarchy's Hyprland compositor, SDDM greeter, Arch package manager, hardware-specific packages, and Omarchy-only applications (`aether`, `omacalc`, `omasnap`, `omawrite`, `owe`) do not map directly to Zorin. Zorin's GNOME desktop supplies the corresponding desktop workflows. Omarchy's service web shortcuts and its theme switcher are not provisioned here; the Zorin AI theme is currently one coordinated fixed palette.

Validation: run `bash -n` and ShellCheck locally. Then run the installer twice on VM 114, verify the package and Flatpak IDs, Herdr launch, and the GNOME Terminal, VSCodium, Herdr, and btop colors. Reboot for shell/menu visuals. An ISO rebuild is required before these changes appear in the bootable image.
