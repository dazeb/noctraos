#!/usr/bin/env python3
"""Render the website's social cards and the X promo images with headless Chrome.

    python3 scripts/render-social.py            # all cards and the favicons
    python3 scripts/render-social.py icons      # favicons only
    python3 scripts/render-social.py og-home x-launch

Output (committed, so the site and the posts need no build step):
  site/img/social/og-*.png     1200x630 Open Graph / X link-preview images, one per page
  assets/promo/x/x-*.png       1600x900 images for posts on X

Cards are plain HTML written to a temp folder, using the real screenshots in site/img/shots/full.
Fonts (Hanken Grotesk, JetBrains Mono, the same as the site) are the local files in
assets/social/fonts, so rendering needs no network. Needs google-chrome (or chromium) and Pillow
(for the size check and PNG optimisation).
"""
import html
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "site/img/shots/full"
LOGO_MARK = ('<svg viewBox="1 4 30 24" aria-hidden="true"><polygon points="2,26 13,6 18,16" fill="#ff6a13"/>'
             '<polygon points="13,26 22,10 30,26" fill="#ff6a13" opacity="0.55"/></svg>')
WIN_LOGO = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M3 5.2 10.4 4v7.2H3zM11.6 3.8 21 '
            '2.4v8.8h-9.4zM3 12.4h7.4v7.2L3 18.4zM11.6 12.4H21v9.2l-9.4-1.4z"/></svg>')
CMD_LOGO = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.8" '
            'stroke-linecap="round" stroke-linejoin="round" d="M15 6v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V6a3 3 0 1 0-3 '
            '3h12a3 3 0 1 0-3-3"/></svg>')
ONE_LINER = "bash <(curl -sSfL https://raw.githubusercontent.com/dazeb/noctraos/main/proxmox-install.sh)"

FONTS = ROOT / "assets/social/fonts"

CSS = """
@font-face{font-family:'Hanken Grotesk';font-weight:100 900;src:url('file://@FONTS@/HankenGrotesk-var.woff2') format('woff2')}
@font-face{font-family:'JetBrains Mono';font-weight:100 800;src:url('file://@FONTS@/JetBrainsMono-var.woff2') format('woff2')}
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0b0a09;--panel:#100f0d;--raised:#1a1816;--line:#2a2723;--fg:#f0ece6;--muted:#a39d95;--amber:#ff6a13;--amber-hot:#ff8a3d}
html,body{width:var(--w);height:var(--h);overflow:hidden;background:var(--bg);color:var(--fg);
  font-family:'Hanken Grotesk',system-ui,sans-serif;-webkit-font-smoothing:antialiased}
body{position:relative}
.glow{position:absolute;inset:0;background:
  radial-gradient(60% 80% at 88% 8%,rgba(255,106,19,.20),transparent 62%),
  radial-gradient(50% 60% at 6% 108%,rgba(255,106,19,.11),transparent 60%)}
.grid{position:absolute;inset:0;opacity:.5;background-image:linear-gradient(var(--line) 1px,transparent 1px),
  linear-gradient(90deg,var(--line) 1px,transparent 1px);background-size:64px 64px;
  -webkit-mask-image:radial-gradient(70% 90% at 80% 20%,#000,transparent 75%);mask-image:radial-gradient(70% 90% at 80% 20%,#000,transparent 75%)}
.brand{display:flex;align-items:center;gap:calc(var(--u)*.7);font-weight:700;font-size:calc(var(--u)*1.7);letter-spacing:-.01em}
.brand svg{height:calc(var(--u)*1.6);width:auto}
.brand small{font-size:.78em;color:var(--muted);font-weight:600;letter-spacing:.02em}
h1{font-weight:800;letter-spacing:-.03em;line-height:1.02}
h1 em{font-style:normal;color:var(--amber)}
.sub{color:var(--muted);line-height:1.38;font-weight:500}
.chips{display:flex;flex-wrap:wrap;gap:calc(var(--u)*.6)}
.chip{font:500 calc(var(--u)*.95)/1 'JetBrains Mono',monospace;color:var(--fg);padding:calc(var(--u)*.55) calc(var(--u)*.9);
  border:1px solid var(--line);border-radius:999px;background:rgba(26,24,22,.8);white-space:nowrap}
.chip b{color:var(--amber-hot);font-weight:700}
.win{position:absolute;border-radius:calc(var(--u)*1.1);overflow:hidden;border:1px solid #3a3631;
  box-shadow:0 30px 80px rgba(0,0,0,.65),0 0 0 1px rgba(255,255,255,.02),0 0 120px rgba(255,106,19,.12);background:#000}
.win img{display:block;width:100%;height:100%;object-fit:cover}
.term{position:absolute;border-radius:calc(var(--u)*1.1);border:1px solid #3a3631;background:#070605;overflow:hidden;
  box-shadow:0 30px 80px rgba(0,0,0,.65),0 0 120px rgba(255,106,19,.12)}
.term .bar{display:flex;gap:calc(var(--u)*.55);padding:calc(var(--u)*.9) calc(var(--u)*1.1);border-bottom:1px solid var(--line);background:#100f0d}
.term .bar i{width:calc(var(--u)*.8);height:calc(var(--u)*.8);border-radius:50%;background:#2e2a26}
.term pre{font:500 calc(var(--u)*1.12)/1.55 'JetBrains Mono',monospace;color:#eaeaea;white-space:pre-wrap;word-break:break-all;padding:calc(var(--u)*1.4)}
.term pre .p{color:var(--amber)}.term pre .c{color:#8f8a83}.term pre .ok{color:#7fd28a}
.keys{display:flex;align-items:center;gap:calc(var(--u)*1)}
.key{display:grid;place-items:center;min-width:calc(var(--u)*5.2);height:calc(var(--u)*4.6);padding:0 calc(var(--u)*1.4);
  border-radius:calc(var(--u)*.9);background:linear-gradient(#2a2622,#1a1816);border:1px solid #3a3631;
  box-shadow:0 calc(var(--u)*.35) 0 #0b0a09,0 calc(var(--u)*.8) calc(var(--u)*1.6) rgba(0,0,0,.5);
  font:600 calc(var(--u)*1.7)/1 'Hanken Grotesk',sans-serif;color:var(--fg)}
.key svg{height:calc(var(--u)*2.1);width:auto}
.plus{font-size:calc(var(--u)*2);color:var(--muted)}
.url{font:500 calc(var(--u)*1.05)/1 'JetBrains Mono',monospace;color:var(--muted)}
.url b{color:var(--fg);font-weight:700}
"""


def page(w, h, u, body):
    return (f"<!doctype html><meta charset=utf-8><style>:root{{--w:{w}px;--h:{h}px;--u:{u}px}}{CSS}</style>"
            f"<body><div class=glow></div><div class=grid></div>{body}</body>").replace("@FONTS@", str(FONTS))


def shot(name):
    return f'file://{SHOTS / (name + ".webp")}'


def crop(name):
    """The tighter crops the website uses (the panel fills the frame); readable at card size."""
    return f'file://{SHOTS.parent / (name + ".webp")}'


def chips(items, extra=""):
    return '<div class="chips" ' + extra + ">" + "".join(f'<span class="chip">{i}</span>' for i in items) + "</div>"


# ---- Open Graph cards (1200x630) --------------------------------------------------------------
def og(title_html, sub, visual, foot_chips):
    u = 14
    body = f"""
<div style="position:absolute;left:64px;top:54px;width:560px">
  <div class="brand">{LOGO_MARK}<span>Noctra <small>OS</small></span></div>
  <h1 style="margin-top:62px;font-size:60px">{title_html}</h1>
  <p class="sub" style="margin-top:22px;font-size:25px;max-width:500px">{html.escape(sub)}</p>
</div>
<div style="position:absolute;left:64px;bottom:50px">{chips(foot_chips)}</div>
{visual}
<div class="url" style="position:absolute;right:64px;bottom:50px;font-size:17px"><b>noctraos.dev</b></div>"""
    return page(1200, 630, u, body)


def og_shot(name, pos="50% 50%", h=438):
    return (f'<div class="win" style="left:640px;top:{96 + (438 - h) // 2}px;width:496px;height:{h}px">'
            f'<img src="{crop(name)}" style="object-position:{pos}"></div>')


def og_term():
    return f"""<div class="term" style="left:640px;top:96px;width:496px">
<div class="bar"><i></i><i></i><i></i></div>
<pre style="word-break:normal;overflow-wrap:anywhere"><span class="c"># on the Proxmox host, as root</span>
<span class="p">$</span> {html.escape(ONE_LINER).replace("/", "/<wbr>")}

<span class="ok">✓</span> checks the download
<span class="ok">✓</span> creates a UEFI VM</pre></div>"""


CARDS = {
    "og-home": (1200, 630, "site/img/social", lambda: og(
        "An <em>AI</em> development workstation OS.",
        "Local models and AI coding assistants, one click from Start. Super + Space finds anything.",
        og_shot("desktop", "64% 78%"), ["Free download", "Based on Ubuntu 24.04", "0.3.2"])),
    "og-features": (1200, 630, "site/img/social", lambda: og(
        "Search, assistants and local AI, <em>set up</em> for you.",
        "A calm dark desktop with Hermes, Codex, Claude Code, OpenCode, Grok, Gemini CLI and Qwen Code in the Start panel.",
        og_shot("start-panel", "50% 50%", 310), ["Super + Space", "Local models", "Dark + amber"])),
    "og-download": (1200, 630, "site/img/social", lambda: og(
        "Get <em>NoctraOS</em> 0.3.2",
        "The installer ISO, VM disks for KVM, VMware and VirtualBox, and a one-command Proxmox installer.",
        og_term(), ["ISO", "QCOW2", "VMDK", "Proxmox"])),
    "og-community": (1200, 630, "site/img/social", lambda: og(
        "Help build <em>NoctraOS</em>",
        "Try it, report what is confusing, improve the docs, or send a fix. First contributions are welcome.",
        og_shot("welcome-map", "50% 50%", 310), ["Issues", "Docs", "Pull requests"])),
}


# ---- X promo images (1600x900) ----------------------------------------------------------------
def x_card(inner, u=18):
    return page(1600, 900, u, inner)


def x_launch():
    return x_card(f"""
<div style="position:absolute;left:84px;top:70px"><div class="brand" style="font-size:34px">{LOGO_MARK}<span>Noctra <small>OS</small></span></div></div>
<h1 style="position:absolute;left:84px;top:180px;width:680px;font-size:92px">NoctraOS <em>0.3.2</em><br>is out.</h1>
<p class="sub" style="position:absolute;left:84px;top:470px;width:600px;font-size:33px">An AI development workstation OS. Local AI and coding assistants, ready when you are.</p>
<div style="position:absolute;left:84px;bottom:76px">{chips(["ISO", "VM disks", "Proxmox script"])}</div>
<div class="win" style="left:730px;top:140px;width:790px;height:444px"><img src="{shot('desktop')}"></div>
<div class="url" style="position:absolute;right:84px;bottom:76px;font-size:24px"><b>noctraos.dev</b></div>""", 20)


def x_search():
    return x_card(f"""
<div style="position:absolute;left:84px;top:70px"><div class="brand" style="font-size:34px">{LOGO_MARK}<span>Noctra <small>OS</small></span></div></div>
<div class="keys" style="position:absolute;left:84px;top:200px;--u:20px"><span class="key">{WIN_LOGO}</span><span class="plus">or</span><span class="key">{CMD_LOGO}</span><span class="plus">+</span><span class="key" style="min-width:170px">Space</span></div>
<h1 style="position:absolute;left:84px;top:350px;width:640px;font-size:84px">Find <em>anything</em> from one box.</h1>
<p class="sub" style="position:absolute;left:84px;top:640px;width:600px;font-size:32px">Apps, files, clipboard history and the web. No hunting through menus.</p>
<div class="win" style="left:800px;top:100px;width:720px;height:450px"><img src="{crop('search-apps')}"></div>
<div class="win" style="left:880px;top:480px;width:640px;height:360px"><img src="{crop('search-files')}"></div>
<div class="url" style="position:absolute;left:84px;bottom:76px;font-size:24px"><b>noctraos.dev</b></div>""", 20)


def x_proxmox():
    return x_card(f"""
<div style="position:absolute;left:84px;top:70px"><div class="brand" style="font-size:34px">{LOGO_MARK}<span>Noctra <small>OS</small></span></div></div>
<h1 style="position:absolute;left:84px;top:170px;width:1300px;font-size:104px">One command. <em>One VM.</em></h1>
<p class="sub" style="position:absolute;left:84px;top:330px;width:1100px;font-size:34px">Run it on the Proxmox host. It asks for RAM, cores and storage, checks the download and builds a UEFI VM.</p>
<div class="term" style="left:84px;top:450px;width:1432px;--u:21px"><div class="bar"><i></i><i></i><i></i></div>
<pre style="font-size:22px;white-space:pre;line-height:1.7"><span class="p">$</span> {html.escape(ONE_LINER)}
<span class="ok">OK:</span> noctraos-0.3.2.qcow2 matches SHA256SUMS
<span class="ok">VM 100 is running.</span></pre></div>
<div style="position:absolute;left:84px;bottom:76px">{chips(["Proxmox VE 8 and 9", "Ready-made disk or installer ISO", "SHA-256 checked"])}</div>
<div class="url" style="position:absolute;right:84px;bottom:76px;font-size:24px"><b>noctraos.dev</b></div>""", 20)


def x_ai():
    names = ["Hermes", "Codex", "Claude Code", "OpenCode", "Grok", "Gemini CLI", "Qwen Code"]
    return x_card(f"""
<div style="position:absolute;left:84px;top:70px"><div class="brand" style="font-size:34px">{LOGO_MARK}<span>Noctra <small>OS</small></span></div></div>
<h1 style="position:absolute;left:84px;top:170px;width:700px;font-size:88px">AI on your <em>own</em> computer.</h1>
<p class="sub" style="position:absolute;left:84px;top:470px;width:640px;font-size:31px">Local models through Ollama, plus Hermes and six coding assistants one click from the Start button.</p>
<div style="position:absolute;left:84px;top:650px;width:660px">{chips(names)}</div>
<div class="win" style="left:790px;top:170px;width:730px;height:456px"><img src="{crop('start-panel')}"></div>
<div class="url" style="position:absolute;left:84px;bottom:76px;font-size:24px"><b>noctraos.dev</b></div>""", 20)


for name, fn, folder in (("x-launch", x_launch, "assets/promo/x"), ("x-search", x_search, "assets/promo/x"),
                         ("x-proxmox", x_proxmox, "assets/promo/x"), ("x-ai", x_ai, "assets/promo/x")):
    CARDS[name] = (1600, 900, folder, fn)


# ---- favicons and app icons -------------------------------------------------------------------
def icon_svg(rounded, scale):
    """The Noctra mark on the site's near-black; `scale` is the share of the square the mark fills."""
    pad = (1 - scale) / 2 * 32
    inner = 32 * scale
    rx = ' rx="7"' if rounded else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32"{rx} fill="#0b0a09"/>'
            f'<svg x="{pad:.2f}" y="{pad:.2f}" width="{inner:.2f}" height="{inner:.2f}" viewBox="1 4 30 24">'
            f'<polygon points="2,26 13,6 18,16" fill="#ff6a13"/><polygon points="13,26 22,10 30,26" fill="#ff6a13" opacity="0.55"/></svg></svg>')


def render_icons():
    from PIL import Image
    site = ROOT / "site"
    (site / "favicon.svg").write_text(icon_svg(True, 0.78) + "\n")
    with tempfile.TemporaryDirectory() as tmp:
        made = {}
        for name, size, scale in (("apple-touch-icon.png", 180, 0.62), ("icon-192.png", 192, 0.6), ("icon-512.png", 512, 0.6),
                                  ("favicon-48.png", 48, 0.78)):
            src = Path(tmp) / "i.html"
            src.write_text(f"<!doctype html><style>*{{margin:0}}html,body{{width:{size}px;height:{size}px;overflow:hidden;background:#0b0a09}}"
                           f"svg{{display:block;width:{size}px;height:{size}px}}</style>{icon_svg(False, scale)}")
            out = Path(tmp) / name
            subprocess.run([chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                            "--force-device-scale-factor=1", f"--window-size={size},{size}", f"--screenshot={out}",
                            f"file://{src}"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            im = Image.open(out).convert("RGB").crop((0, 0, size, size))
            made[name] = im
        for name in ("apple-touch-icon.png", "icon-192.png", "icon-512.png"):
            made[name].save(site / name, optimize=True)
        made["favicon-48.png"].save(site / "favicon.ico", sizes=[(48, 48), (32, 32), (16, 16)])
    for f in ("favicon.svg", "favicon.ico", "apple-touch-icon.png", "icon-192.png", "icon-512.png"):
        print(f"site/{f}  {(site / f).stat().st_size} bytes")


def chrome():
    for c in ("google-chrome", "chromium", "chromium-browser"):
        p = shutil.which(c)
        if p:
            return p
    sys.exit("no google-chrome or chromium on PATH")


def render(name):
    w, h, folder, fn = CARDS[name]
    out = ROOT / folder / f"{name}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"{name}.html"
        src.write_text(fn())
        shot_path = Path(tmp) / "shot.png"
        subprocess.run([chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1", f"--window-size={w},{h}", "--virtual-time-budget=12000",
                        f"--screenshot={shot_path}", f"file://{src}"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        from PIL import Image
        im = Image.open(shot_path).convert("RGB")
        if im.size != (w, h):                       # headless windows can come out a few px short
            canvas = Image.new("RGB", (w, h), (11, 10, 9))
            canvas.paste(im, (0, 0))
            im = canvas
        im.save(out, optimize=True)
    print(f"{out.relative_to(ROOT)}  {w}x{h}  {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    wanted = sys.argv[1:] or list(CARDS) + ["icons"]
    for n in wanted:
        if n == "icons":
            render_icons()
            continue
        if n not in CARDS:
            sys.exit(f"unknown card {n}; choose from: {', '.join(CARDS)}")
        render(n)
