#!/usr/bin/env python3
"""Render the artwork of the kubuntu flavour (KDE Plasma) with headless Chrome.

    python3 scripts/render-kubuntu-branding.py               # everything
    python3 scripts/render-kubuntu-branding.py calamares     # one group: calamares, login, splash, previews

Output (committed, so building the ISO or installing needs none of this):
  assets/boot/calamares/        the installer: logo.png (sidebar), icon.png (window), welcome.png (first page) and the
                                six slides shown while it copies files (slide-01.png .. slide-06.png, 2400x1350)
  assets/plasma/login/          background.jpg (3840x2160, the SDDM login and the lock screen) and logo.png (the lockup
                                SDDM shows while the login screen is idle)
  assets/plasma/look-and-feel/dev.noctraos.desktop/contents/
                                splash/images/lockup.png (the Plasma splash after login), previews/ (System Settings >
                                Global Theme)

The identity is the website's: the two-peak mark (#ff6a13) and the "Noctra OS" wordmark in Hanken Grotesk; the canvas,
lines and accent are the desktop palette (configs/theme/palette.json), with JetBrains Mono for keys and labels, the same as
the zorin flavour's installer slideshow. Corners are square (palette radius 0). Fonts are the local files in
assets/social/fonts, so rendering needs no network. Needs google-chrome (or chromium) and Pillow. Rerun after changing
the palette, the mark, a slide text or the default wallpaper.
"""
import html
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets/social/fonts"
PALETTE = json.loads((ROOT / "configs/theme/palette.json").read_text())["colors"]
CALAMARES = ROOT / "assets/boot/calamares"
LOGIN = ROOT / "assets/plasma/login"
LNF = ROOT / "assets/plasma/look-and-feel/dev.noctraos.desktop/contents"
DEFAULT_WALLPAPER = ROOT / "assets/wallpapers/noctraos-sunset-peaks-2160p.jpg"   # install/desktop/plasma/06 sets this one
LOGO = "#ff6a13"                                                                 # assets/icons/noctraos-logo.svg

MARK = (f'<svg class="mark" viewBox="1 4 30 24" aria-hidden="true"><polygon points="2,26 13,6 18,16" fill="{LOGO}"/>'
        f'<polygon points="13,26 22,10 30,26" fill="{LOGO}" opacity="0.55"/></svg>')
WIN_KEY = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M3 4.6 10.2 3.6v7.2H3zM11.2 3.5 21 '
           '2v8.8h-9.8zM3 12.2h7.2v7.2L3 18.4zM11.2 12.2H21V22l-9.8-1.4z"/></svg>')
SEARCH = ('<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" '
          'stroke-width="2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2" stroke-linecap="square"/></svg>')

CSS = """
@font-face{font-family:'Hanken Grotesk';font-weight:100 900;src:url('file://@FONTS@/HankenGrotesk-var.woff2') format('woff2')}
@font-face{font-family:'JetBrains Mono';font-weight:100 800;src:url('file://@FONTS@/JetBrainsMono-var.woff2') format('woff2')}
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:@background@;--panel:@panel@;--raised:@raised@;--sel:@selection@;--line:@border@;--fg:@foreground@;
  --bright:#eaeaea;--muted:@muted@;--accent:@accent@;--logo:@LOGO@}
html,body{width:var(--w);height:var(--h);overflow:hidden;background:var(--page,var(--bg));color:var(--fg);
  font-family:'Hanken Grotesk',system-ui,sans-serif;-webkit-font-smoothing:antialiased}
body{position:relative}
.mono{font-family:'JetBrains Mono',monospace}
.glow{position:absolute;inset:0;pointer-events:none}
.grid{position:absolute;inset:0;opacity:.55;background-image:linear-gradient(var(--line) 1px,transparent 1px),
  linear-gradient(90deg,var(--line) 1px,transparent 1px);background-size:64px 64px}
.lockup{display:flex;align-items:center;gap:.42em;font-weight:700;letter-spacing:-.01em;color:var(--bright);white-space:nowrap}
.lockup .mark{height:1.02em;width:auto;flex:none;transform:translateY(-.02em)}
.lockup small{font-size:.74em;font-weight:500;color:var(--muted);letter-spacing:.05em}
.key{display:inline-flex;align-items:center;justify-content:center;gap:.5em;padding:.62em 1em;background:var(--raised);
  border:1px solid var(--line);border-bottom:3px solid var(--accent);color:var(--bright);
  font:500 1em/1 'JetBrains Mono',monospace;white-space:nowrap}
.key svg{height:1.2em;width:auto}
"""


def css():
    out = CSS.replace("@FONTS@", str(FONTS)).replace("@LOGO@", LOGO)
    for name, value in PALETTE.items():
        out = out.replace(f"@{name}@", value)
    return out


def page(w, h, body, extra_css="", transparent=False):
    page_bg = "--page:transparent;" if transparent else ""
    return (f"<!doctype html><meta charset=utf-8><style>:root{{--w:{w}px;--h:{h}px;{page_bg}}}{css()}{extra_css}</style>"
            f"<body>{body}</body>")


def chrome():
    for c in ("google-chrome", "chromium", "chromium-browser"):
        p = shutil.which(c)
        if p:
            return p
    sys.exit("no google-chrome or chromium on PATH")


def render(markup, out, w, h, scale=1, transparent=False, quality=90, resize=None):
    """Screenshot one HTML page at w x h CSS pixels times scale (then resized to `resize`, a width x height pair, if
    given); PNG (alpha kept when transparent) or JPEG by suffix."""
    from PIL import Image
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "page.html"
        src.write_text(markup)
        shot = Path(tmp) / "shot.png"
        args = [chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                f"--force-device-scale-factor={scale}", f"--window-size={w},{h}", "--virtual-time-budget=8000",
                f"--screenshot={shot}"]
        if transparent:
            args.append("--default-background-color=00000000")
        subprocess.run(args + [f"file://{src}"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        size = (round(w * scale), round(h * scale))
        im = Image.open(shot).convert("RGBA")
        if im.size != size:                         # headless windows can come out a few px short
            canvas = Image.new("RGBA", size, (0, 0, 0, 0))
            canvas.paste(im, (0, 0))
            im = canvas
        if resize:
            im = im.resize(resize, Image.LANCZOS)
            size = resize
        if out.suffix == ".jpg":
            im.convert("RGB").save(out, quality=quality, optimize=True, progressive=True)
        elif transparent:
            im.save(out, optimize=True)
        else:
            im.convert("RGB").save(out, optimize=True)
    print(f"{out.relative_to(ROOT)}  {size[0]}x{size[1]}  {out.stat().st_size // 1024} KB")


def lockup_png(out, height_px, scale=2):
    """Mark + wordmark on a transparent canvas, cropped to its ink (Chrome sizes the page, Pillow trims it)."""
    from PIL import Image
    font_px = height_px * 0.62
    w = int(height_px * 5.2)
    markup = page(w, height_px, f'<div class="lockup" style="font-size:{font_px}px;position:absolute;left:{height_px * .1}px;'
                  f'top:50%;transform:translateY(-50%)">{MARK}<span>Noctra <small>OS</small></span></div>', transparent=True)
    render(markup, out, w, height_px, scale=scale, transparent=True)
    im = Image.open(out)
    box = im.getchannel("A").getbbox()
    pad = int(height_px * scale * 0.06)
    im.crop((max(box[0] - pad, 0), 0, min(box[2] + pad, im.width), im.height)).save(out, optimize=True)
    print(f"  trimmed to {Image.open(out).size[0]}x{Image.open(out).size[1]}")


# --- the installer (Calamares) ------------------------------------------------------------------------------------------

def calamares_logo():
    # Sidebar logo: the mark alone, drawn into the middle of a transparent square (Calamares scales it to the sidebar).
    render(page(128, 128, f'<div style="position:absolute;inset:18px 12px">{MARK.replace("<svg ", "<svg style=width:100%;height:100% ")}'
                          f'</div>', transparent=True), CALAMARES / "logo.png", 128, 128, transparent=True)


def calamares_icon():
    # Window icon: the site's app icon (mark on the canvas colour), square corners like the rest of the desktop.
    render(page(512, 512, f'<div class="glow" style="background:radial-gradient(70% 70% at 50% 62%,rgba(255,106,19,.16),'
                          f'transparent 70%)"></div><div style="position:absolute;inset:118px 96px">'
                          f'{MARK.replace("<svg ", "<svg style=width:100%;height:100% ")}</div>'),
           CALAMARES / "icon.png", 512, 512)


def calamares_welcome():
    # First page picture (Kubuntu's is 800x300). Opaque, because the installer's own colours are light in the live session.
    body = f"""
<div class="glow" style="background:radial-gradient(55% 90% at 50% 118%,rgba(255,106,19,.30),transparent 70%),
  radial-gradient(40% 60% at 92% -10%,rgba(230,142,13,.10),transparent 70%)"></div>
<div class="grid" style="-webkit-mask-image:radial-gradient(60% 80% at 50% 100%,#000,transparent 80%)"></div>
<div style="position:absolute;inset:0;border:1px solid var(--line)"></div>
<div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:22px">
  <div class="lockup" style="font-size:64px">{MARK}<span>Noctra <small>OS</small></span></div>
  <div class="mono" style="font-size:15px;letter-spacing:.32em;text-transform:uppercase;color:var(--muted)">
    The AI development workstation</div>
</div>
<div style="position:absolute;left:50%;bottom:0;width:120px;height:3px;margin-left:-60px;background:var(--accent)"></div>"""
    render(page(800, 300, body), CALAMARES / "welcome.png", 800, 300)


SLIDE_CSS = """
.slide{position:absolute;inset:0}
.top{position:absolute;left:96px;right:96px;top:64px;display:flex;align-items:center;justify-content:space-between}
.top .lockup{font-size:30px}
.count{font:500 16px/1 'JetBrains Mono',monospace;color:var(--muted);letter-spacing:.2em}
.count b{color:var(--accent);font-weight:600}
.copy{position:absolute;left:96px;top:196px;width:700px}
.eyebrow{font:600 15px/1 'JetBrains Mono',monospace;letter-spacing:.3em;text-transform:uppercase;color:var(--accent);margin-bottom:26px}
h1{font-weight:800;font-size:64px;line-height:1.04;letter-spacing:-.03em;color:var(--bright);margin-bottom:26px;text-wrap:balance}
.lead{font-size:25px;line-height:1.42;color:var(--fg);font-weight:500;margin-bottom:40px}
ul{list-style:none;border-top:1px solid var(--line)}
li{position:relative;padding:17px 0 17px 32px;border-bottom:1px solid var(--line);font-size:19px;line-height:1.42;color:var(--muted)}
li:before{content:'';position:absolute;left:0;top:26px;width:10px;height:10px;background:var(--accent)}
li b{color:var(--bright);font-weight:650}
.art{position:absolute;left:880px;right:96px;top:196px;bottom:140px;display:flex;align-items:center;justify-content:center}
.dots{position:absolute;left:96px;bottom:72px;display:flex;gap:10px}
.dots i{width:28px;height:4px;background:var(--line)}
.dots i.on{background:var(--accent)}
.foot{position:absolute;right:96px;bottom:66px;font:500 15px/1 'JetBrains Mono',monospace;color:var(--muted);letter-spacing:.06em}
.win{background:var(--panel);border:1px solid var(--line);box-shadow:0 40px 90px rgba(0,0,0,.55),0 0 140px rgba(230,142,13,.07)}
.row{display:flex;align-items:center;gap:14px;padding:13px 18px;font-size:18px;color:var(--fg)}
.row.sel{background:var(--sel);box-shadow:inset 3px 0 0 var(--accent);color:var(--bright)}
.row img,.row .ic{width:26px;height:26px;flex:none}
.ic{display:inline-block;background:var(--raised);border:1px solid var(--line)}
.hd{padding:16px 18px 8px;font:600 13px/1 'JetBrains Mono',monospace;letter-spacing:.24em;text-transform:uppercase;color:var(--muted)}
.sep{height:1px;background:var(--line);margin:6px 0}
"""


def slide(index, eyebrow, title, lead, points, art):
    bullets = "".join(f"<li><b>{html.escape(b)}</b> {html.escape(t)}</li>" for b, t in points)
    dots = "".join(f'<i class="{"on" if n == index else ""}"></i>' for n in range(1, 7))
    body = f"""
<div class="glow" style="background:radial-gradient(48% 70% at 84% 58%,rgba(230,142,13,.11),transparent 70%),
  radial-gradient(40% 50% at 0% 110%,rgba(255,106,19,.08),transparent 70%)"></div>
<div class="grid" style="-webkit-mask-image:radial-gradient(48% 70% at 82% 50%,#000,transparent 78%)"></div>
<div class="slide">
  <div class="top"><div class="lockup">{MARK}<span>Noctra <small>OS</small></span></div>
    <div class="count"><b>0{index}</b> / 06</div></div>
  <div class="copy"><div class="eyebrow">{html.escape(eyebrow)}</div><h1>{title}</h1>
    <div class="lead">{lead}</div><ul>{bullets}</ul></div>
  <div class="art">{art}</div>
  <div class="dots">{dots}</div>
  <div class="foot">noctraos.dev</div>
</div>"""
    render(page(1600, 900, body, SLIDE_CSS), CALAMARES / f"slide-{index:02d}.png", 1600, 900, scale=1.5)


def icon(name):
    return f'file://{ROOT}/assets/icons/{name}'


def slides():
    # 1 — welcome: the mark, large, on its own horizon.
    slide(1, "Welcome", "Your AI workstation is on its way.",
          "While the files copy, here is what NoctraOS sets up for you.",
          [("It finishes on its own.", "The first time you sign in, NoctraOS sets itself up. Keep it connected to the internet."),
           ("No terminal needed.", "Everything you need day to day works with the mouse."),
           ("You stay in charge.", "Every setup step can be skipped, and nothing updates until you say so.")],
          f'<div style="position:relative;width:560px;height:448px">'
          f'<div style="position:absolute;inset:-60px;background:radial-gradient(50% 50% at 50% 70%,rgba(255,106,19,.22),transparent 70%)"></div>'
          f'{MARK.replace("<svg ", "<svg style=position:absolute;inset:0;width:100%;height:100% ")}'
          f'<div style="position:absolute;left:-40px;right:-40px;bottom:-6px;height:1px;background:var(--line)"></div></div>')

    # 2 — the Start menu (Kickoff) and the panel.
    agents = [("Hermes", None), ("Claude Code", "noctraos-agent-claude.svg"), ("Codex", "noctraos-agent-codex.svg"),
              ("Gemini CLI", "noctraos-agent-gemini.svg")]
    rows = "".join(
        f'<div class="row{" sel" if n == 0 else ""}">'
        + (f'<img src="file://{ROOT}/assets/icons/hermes/hicolor/128x128/apps/hermes.png">' if not f else f'<img src="{icon(f)}">')
        + f"{name}</div>" for n, (name, f) in enumerate(agents))
    panel_icons = "".join(f'<span class="ic" style="width:30px;height:30px"></span>' for _ in range(4))
    slide(2, "The desktop", "Start where you expect it.",
          f'Press the <span class="key" style="font-size:18px;padding:.35em .55em;vertical-align:.12em">{WIN_KEY}</span> '
          "key, or click the logo in the panel, and type.",
          [("One search.", "Apps, settings and files from the Start menu, as you type."),
           ("Agents in the menu.", "Hermes and the coding assistants have a section of their own."),
           ("One click away.", "Files, Terminal, VS Code, Hermes and the Control Panel are pinned to the panel.")],
          f'''<div style="position:relative;width:560px;height:560px">
  <div class="win" style="position:absolute;left:0;top:0;width:430px">
    <div class="row" style="margin:14px;border:1px solid var(--accent);background:var(--raised);color:var(--muted)">
      <span style="width:20px;height:20px;color:var(--muted)">{SEARCH}</span>Search…</div>
    <div class="hd">Agents</div>{rows}
    <div class="sep"></div>
    <div class="row"><span class="ic"></span>Control Panel</div>
    <div class="row" style="padding-bottom:20px"><span class="ic"></span>All applications</div>
  </div>
  <div class="win" style="position:absolute;left:0;right:-40px;bottom:0;height:62px;display:flex;align-items:center;gap:18px;padding:0 18px">
    <span style="display:flex;align-items:center;justify-content:center;width:44px;height:44px;background:var(--sel);box-shadow:inset 0 -3px 0 var(--accent)">
      {MARK.replace("<svg ", "<svg style=width:30px;height:24px ")}</span>{panel_icons}
    <span style="margin-left:auto;font:500 17px/1 'JetBrains Mono',monospace;color:var(--fg)">09:41</span></div>
</div>''')

    # 3 — coding assistants.
    tiles = [("Hermes", f"file://{ROOT}/assets/icons/hermes/hicolor/128x128/apps/hermes.png"),
             ("Claude Code", icon("noctraos-agent-claude.svg")), ("Codex", icon("noctraos-agent-codex.svg")),
             ("OpenCode", icon("noctraos-agent-opencode.svg")), ("Grok", icon("noctraos-agent-grok.svg")),
             ("Gemini CLI", icon("noctraos-agent-gemini.svg")), ("Qwen Code", icon("noctraos-agent-qwen.svg"))]
    grid = "".join(
        f'<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;height:150px;'
        f'background:var(--raised);border:1px solid var(--line);{"border-bottom:3px solid var(--accent);" if n == 0 else ""}'
        f'font:500 16px/1 \'JetBrains Mono\',monospace;color:var(--bright)"><img src="{src}" style="width:48px;height:48px">'
        f"{name}</div>" for n, (name, src) in enumerate(tiles))
    grid += ('<div style="display:flex;align-items:center;justify-content:center;height:150px;border:1px dashed var(--line);'
             'font:500 16px/1.4 \'JetBrains Mono\',monospace;color:var(--muted);text-align:center">installs on<br>first use</div>')
    slide(3, "AI agents", "Coding assistants within reach.",
          "Hermes Desktop comes with NoctraOS. The others install the first time you open them.",
          [("Free to try.", "Hermes’ free tier runs in the Nous cloud, so what you type to it leaves this computer. "
                            "Local-only is one click away."),
           ("Bring your own account.", "Claude Code, Codex and the rest use their own providers and may ask you to sign in."),
           ("Always current.", "The Control Panel shows which version of each you have and updates it.")],
          f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;width:600px">{grid}</div>')

    # 4 — local AI.
    models = [("qwen2.5-coder:7b", "4.7 GB", "Download"), ("qwen2.5-coder:14b", "9.0 GB", "Download"),
              ("llama3.2:3b", "2.0 GB", "Download")]
    mrows = "".join(
        f'<div class="row" style="padding:18px 22px;border-top:1px solid var(--line)"><span class="mono" style="color:var(--bright)">'
        f'{m}</span><span class="mono" style="margin-left:auto;color:var(--muted);font-size:15px">{s}</span>'
        f'<span class="key" style="font-size:14px;padding:.55em .8em;margin-left:14px">{b}</span></div>' for m, s, b in models)
    slide(4, "Local AI", "Local AI, if you want it.",
          "Models can run on this computer through Ollama. Your files and prompts stay here.",
          [("You pick the model.", "Nothing is downloaded for you: set up local AI and choose models under AI models."),
           ("One that fits.", "LLMFIT helps you find a model your memory and graphics card can run."),
           ("The editor is ready.", "VS Code comes with Continue, pointed at your local model.")],
          f'''<div class="win" style="width:600px">
  <div class="row" style="padding:20px 22px;font-weight:700;font-size:21px;color:var(--bright)">AI models
    <span class="mono" style="margin-left:auto;font-size:14px;font-weight:500;color:var(--muted)">Engine</span>
    <span class="mono" style="font-size:14px;color:var(--accent)">● Off</span></div>
  {mrows}
  <div class="row" style="padding:16px 22px;border-top:1px solid var(--line);font-size:15px;color:var(--muted)">
    <span class="mono">Runs on this computer · nothing leaves it</span></div>
</div>''')

    # 5 — the Control Panel.
    pages = ["Overview", "Accounts", "Updates", "Apps", "AI models", "Hardware", "Health", "Privacy", "About"]
    side = "".join(f'<div class="row{" sel" if p == "Health" else ""}" style="padding:11px 18px;font-size:17px">{p}</div>'
                   for p in pages)
    checks = [("GitHub", "Sign in…", False), ("Updates", "Up to date", True), ("Disk space", "212 GB free", True),
              ("Local AI", "Off", True), ("Git identity", "Set up", True)]
    crow = "".join(
        f'<div class="row" style="padding:15px 20px;border-top:1px solid var(--line);font-size:17px">'
        f'<span style="width:10px;height:10px;background:{"var(--muted)" if ok else "var(--accent)"}"></span>{n}'
        f'<span class="mono" style="margin-left:auto;font-size:14px;color:{"var(--muted)" if ok else "var(--accent)"}">{s}</span></div>'
        for n, s, ok in checks)
    slide(5, "Control Panel", "One window for the chores.",
          "Updates, accounts, apps, local AI and health checks, all with the mouse.",
          [("Sign in to GitHub with a short code.", "Accounts sets up Git and GitHub, no terminal."),
           ("Health lists problems first.", "Some have a Fix button."),
           ("Nothing updates on its own.", "Updates waits until you press Update.")],
          f'''<div class="win" style="display:flex;width:620px;height:520px">
  <div style="width:200px;border-right:1px solid var(--line);padding-top:12px;background:var(--bg)">{side}</div>
  <div style="flex:1">
    <div class="row" style="padding:22px 20px 16px;font-weight:700;font-size:22px;color:var(--bright)">Health</div>{crow}
    <div class="row" style="padding:18px 20px"><span class="key" style="font-size:14px;padding:.6em .9em">Check again</span></div>
  </div>
</div>''')

    # 6 — right-click actions and the everyday tools.
    def menu_rows(items):
        return "".join('<div class="sep"></div>' if t is None else
                       f'<div class="row{" sel" if s else ""}" style="padding:12px 18px;font-size:17px">'
                       f'<span class="ic" style="width:20px;height:20px{";border-color:var(--accent)" if s else ""}"></span>{t}'
                       + ('<span style="margin-left:auto;color:var(--muted)">›</span>' if t == "NoctraOS" else "") + "</div>"
                       for t, s in items)
    mrows = menu_rows([("Open with Kate", False), ("Copy location", False), (None, False), ("NoctraOS", True), (None, False),
                       ("Properties", False)])
    srows = menu_rows([("Ask AI to Explain", True), ("Open in VS Code", False), ("Open Terminal Here", False)])
    files = "".join(
        f'<div style="display:flex;flex-direction:column;align-items:center;gap:10px;width:110px;font-size:15px;color:var(--fg)">'
        f'<span style="width:64px;height:76px;background:var(--raised);border:1px solid {"var(--accent)" if n == 1 else "var(--line)"};'
        f'box-shadow:inset 0 14px 0 var(--sel)"></span><span class="mono" style="font-size:13px">{f}</span></div>'
        for n, f in enumerate(["notes.md", "main.py", "README"]))
    slide(6, "Everyday tools", "Right-click and go.",
          "Right-click a file in Dolphin, then NoctraOS, for the AI and developer actions.",
          [("Clipboard history is kept.", "CopyQ remembers what you copied, so you can paste it again later."),
           ("Task Manager is Mission Center.", "Search for it from the Start menu."),
           ("Flatpaks and AppImages just work.", "AppManager installs and updates the AppImages.")],
          f'''<div style="position:relative;width:640px;height:540px">
  <div class="win" style="position:absolute;inset:0 140px 140px 0;display:flex;gap:20px;padding:40px 30px;align-items:flex-start">{files}</div>
  <div class="win" style="position:absolute;left:150px;top:150px;width:260px;padding:6px 0">{mrows}</div>
  <div class="win" style="position:absolute;left:404px;top:232px;width:260px;padding:6px 0">{srows}</div>
</div>''')


# --- login (SDDM) and lock screen --------------------------------------------------------------------------------------

def peaks(points, fill, extra=""):
    return f'<polygon points="{points}" fill="{fill}" {extra}/>'


def login_background():
    # Night over a range drawn from the mark's two peaks, with an amber horizon. The middle stays quiet: SDDM puts the
    # clock, the avatar and the password box there.
    ridge = ("0,1080 0,860 150,800 260,830 420,700 560,790 700,745 860,835 960,770 1080,860 1200,760 1330,690 1460,800 "
             "1600,735 1760,820 1920,760 1920,1080")
    near = ("0,1080 0,960 180,905 330,950 470,880 640,975 800,925 1000,995 1160,915 1340,990 1500,930 1700,985 1920,935 1920,1080")
    body = f"""
<div class="glow" style="background:
  radial-gradient(70% 38% at 50% 86%,rgba(255,106,19,.30),transparent 70%),
  radial-gradient(40% 22% at 50% 82%,rgba(255,150,60,.20),transparent 70%),
  linear-gradient(180deg,#0a0a0a 0%,#101010 55%,#1a120b 100%)"></div>
<div class="grid" style="opacity:.32;-webkit-mask-image:linear-gradient(180deg,transparent 0%,#000 30%,#000 60%,transparent 80%)"></div>
<svg viewBox="0 0 1920 1080" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%">
  <defs>
    <linearGradient id="far" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2a1a0e"/><stop offset="1" stop-color="#140f0b"/></linearGradient>
    <linearGradient id="nr" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#121010"/><stop offset="1" stop-color="#0b0a0a"/></linearGradient>
  </defs>
  {peaks(ridge, "url(#far)")}
  <polyline points="{ridge.split(' ', 1)[1].rsplit(' ', 1)[0]}" fill="none" stroke="{LOGO}" stroke-opacity=".55" stroke-width="1.2"/>
  {peaks(near, "url(#nr)")}
</svg>
<div style="position:absolute;inset:0;background:radial-gradient(120% 90% at 50% 40%,transparent 55%,rgba(0,0,0,.55) 100%)"></div>"""
    render(page(1920, 1080, body), LOGIN / "background.jpg", 1920, 1080, scale=2, quality=88)


def login_logo():
    lockup_png(LOGIN / "logo.png", 64)


# --- Plasma splash and the Global Theme previews -----------------------------------------------------------------------

def splash_lockup():
    lockup_png(LNF / "splash/images/lockup.png", 96)


def previews():
    # What System Settings > Global Theme shows: the default wallpaper, the floating panel, the Start button.
    panel_icons = "".join('<span style="width:30px;height:30px;background:rgba(255,255,255,.10)"></span>' for _ in range(5))
    body = f"""
<img src="file://{DEFAULT_WALLPAPER}" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover">
<div style="position:absolute;left:24px;right:24px;bottom:16px;height:56px;background:rgba(13,13,13,.92);border:1px solid var(--line);
  display:flex;align-items:center;gap:16px;padding:0 14px">
  <span style="display:flex;align-items:center;justify-content:center;width:42px;height:42px;background:var(--sel)">
    {MARK.replace("<svg ", "<svg style=width:30px;height:24px ")}</span>{panel_icons}
  <span style="margin-left:auto;font:500 18px/1 'JetBrains Mono',monospace;color:var(--fg)">09:41</span></div>"""
    render(page(1920, 1080, body), LNF / "previews/fullscreenpreview.jpg", 1920, 1080, quality=88)
    render(page(1920, 1080, body), LNF / "previews/preview.png", 1920, 1080, resize=(640, 360))
    splash = f"""<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center">
  <div class="lockup" style="font-size:60px">{MARK}<span>Noctra <small>OS</small></span></div></div>
  <div style="position:absolute;left:50%;top:62%;width:240px;margin-left:-120px;height:3px;background:var(--line)">
  <div style="width:62%;height:100%;background:var(--accent)"></div></div>"""
    render(page(1920, 1080, splash), LNF / "previews/splash.png", 1920, 1080, resize=(640, 360))
    render(page(1920, 1080, f'<img src="file://{(LOGIN / "background.jpg")}" style="position:absolute;inset:0;width:100%;'
                            f'height:100%;object-fit:cover">'), LNF / "previews/lockscreen.png", 1920, 1080, resize=(640, 360))


GROUPS = {
    "calamares": [calamares_logo, calamares_icon, calamares_welcome, slides],
    "login": [login_background, login_logo],
    "splash": [splash_lockup],
    "previews": [previews],
}

if __name__ == "__main__":
    wanted = sys.argv[1:] or list(GROUPS)
    for g in wanted:
        if g not in GROUPS:
            sys.exit(f"unknown group {g}; choose from: {', '.join(GROUPS)}")
        for fn in GROUPS[g]:
            fn()
