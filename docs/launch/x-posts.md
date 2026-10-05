# NoctraOS 0.3.0 launch posts (X)

Plain, accurate, no hashtags. Every claim below is something the release does today. Images are in
`assets/promo/x/` (1600x900 PNG, under 300 KB each); `scripts/render-social.py` regenerates them.
Link previews use the Open Graph cards in `site/img/social/`, so a post that only contains
`https://noctraos.dev` still gets a large card.

Handles are not filled in: add the project's X handle where it says `@handle` if you want a mention.

## The thread

**1. Announcement** (image: `x-launch.png`)

```
NoctraOS 0.3.0 is out.

A Linux desktop for people moving from Windows. Start button, dock, Windows + Space search, and local AI with coding assistants one click away.

Early release, tested in VMs. ISO, VM disks and a Proxmox script:
https://noctraos.dev
```

Alt text: *NoctraOS 0.3.0 is out. A dark desktop with an amber sun over low-poly mountains, a dock at the bottom, and chips for ISO, VM disks and Proxmox script.*

**2. Search** (image: `x-search.png`)

```
Windows + Space opens one search box: apps, files, clipboard history and the web.

It's the one shortcut the desktop is built around, so you don't hunt through menus.
```

Alt text: *The Windows key plus Space, with two search windows: one finding apps for "code", one finding a file called "planning".*

**3. AI** (image: `x-ai.png`)

```
AI on your own computer. Ollama runs local models and VS Code is pointed at them. Hermes plus six coding assistants (Codex, Claude Code, OpenCode, Grok, Gemini CLI, Qwen Code) are in the Start panel.

Hermes' free tier is Nous's cloud. Local-only is one switch.
```

Alt text: *The NoctraOS Start panel with Hermes, Claude Code, Codex, OpenCode, Grok, Gemini CLI and Qwen Code launchers and a list of recent files.*

**4. Proxmox** (image: `x-proxmox.png`)

```
On Proxmox? Run this on the host:

bash <(curl -sSfL https://raw.githubusercontent.com/dazeb/noctraos/main/proxmox-install.sh)

It asks for RAM, cores and storage, checks the download against SHA256SUMS, and builds a UEFI VM from the ready-made disk or the installer ISO.
```

Alt text: *A terminal showing the one-line install command, then "OK: noctraos-0.3.0.qcow2 matches SHA256SUMS" and "VM 100 is running."*

**5. What to expect** (no image)

```
What to expect: early release, run in VMs (KVM, Proxmox) with little real-hardware testing. First login needs internet and 25 to 40 minutes for AI tool setup. Back up before installing.

Independent project on Zorin OS 18.1 / Ubuntu 24.04, not affiliated with Zorin or Canonical.
```

**6. Contact** (no image)

```
Bugs and ideas: https://github.com/dazeb/noctraos/issues
Questions, press, security reports: admin@noctraos.dev

The source is on GitHub. Tell us what broke.
```

## Standalone posts

For later days, one idea each.

**Coming from Windows** (image: `x-search.png`)

```
Curious about Linux but not about a new set of habits? NoctraOS has a Start button, a dock and Windows + Space search. The AI tools are there when you want them.

Free download: https://noctraos.dev
```

**For developers** (image: `x-ai.png`)

```
A Linux desktop with Ollama, VS Code and Continue already wired together, and Hermes plus six coding assistants in the Start panel.

Install once, start coding. NoctraOS 0.3.0: https://noctraos.dev
```

**Homelab** (image: `x-proxmox.png`)

```
Proxmox homelab? One command on the host gives you a NoctraOS VM, from a ready-made disk or the installer ISO. SHA-256 checked, cleans up after itself if anything fails.

https://noctraos.dev/download
```

**Verify your download** (no image)

```
Large downloads should be checked. Every NoctraOS file has a SHA-256 on the download page and in SHA256SUMS:

sha256sum -c SHA256SUMS --ignore-missing

https://noctraos.dev/download
```

## Posting notes

- Post 1 carries the image and the only link; replies stay short. Pin post 1.
- Use the numbers as they are. The VM disks sign in as `noctraos` / `noctraos` (trial use), and "free" means free to download: no licence has been chosen yet, so avoid "open source".
- X caches link cards. If a card looks stale after the site deploys, post the link once in a draft or add `?v=2` to the URL.
