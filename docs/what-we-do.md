# What NoctraOS does, and what is yours

NoctraOS sets up the system, then you take control. This page says where that line is, so nothing here comes as a surprise.

## What we set up

When you install, NoctraOS prepares a complete AI workstation so you do not have to:

- **The desktop.** The dark and amber theme, the dock and Start panel, and **Super + Space** search for apps, files, clipboard history and the web.
- **The everyday apps.** A browser, office apps, media tools, a task manager, VS Code, and support for Flatpaks and AppImages.
- **Programming languages and tools.** Node, Python and Go through mise, plus terminal tools such as lazygit and Starship.
- **Hermes Desktop**, an AI assistant that works on first launch. Its free tier is a cloud service, so what you type there leaves your computer. The Privacy page switches it to local only.
- **Launchers for the coding agents** (Codex, Claude Code, OpenCode, Grok, Gemini CLI, Qwen Code) in the Start panel.
- **Guest tools** when NoctraOS runs inside a virtual machine.

## What stays yours

- **The coding agents.** A launcher installs the program the first time you open it. Signing in, API keys, subscriptions and each tool's own settings are yours: we do not set them up, store them or manage them.
- **Your AI models.** No model is downloaded until you pick one on the AI models page.
- **Local AI itself.** It is not part of the install. You set it up from the AI models page when you want it, and only then does the GPU driver step get offered, with a summary and a yes first.
- **Whether Ollama starts with your computer.** It does not, unless you turn that on (AI models page, "Start with this computer", or `noc llm autostart on`). Start and stop it there whenever you like. A computer that already had Ollama set up keeps whatever it had.
- **Git and GitHub.** Git will not save your work without a name, and GitHub needs you signed in before you can push, so the Control Panel offers to do both in a minute, with no terminal and no token to copy. Each has a "No, I'll set it up myself" button, and after that nothing nags you.
- **Your files, projects and settings.** Starting settings (for example VS Code's) are only written if you do not have them yet. Updates are built not to override a choice you made.

## Set up without asking, and how to change it

A few things are on from the start. The Privacy page explains each one, and most have a switch there:

| What | Why it is on | Change it |
| --- | --- | --- |
| Remote login (an SSH server) | So you can reach the machine from another computer | Privacy page, or `noc privacy remote off` |
| Clipboard history kept by CopyQ | Super + Space searches it | Privacy page, or `noc privacy clipboard clear` |
| Saved passwords not locked by a password | You sign in automatically, so there is no password to unlock them with | Privacy page explains the trade-off |
| Hermes uses the Nous cloud free tier | It works with no account | Privacy page, or `noc privacy hermes local` |

## Updates

- **NoctraOS updates never install by themselves.** A daily check can tell you an update is waiting. You install it from the Updates page (or `noc update`), and you can pick which parts. To stop the reminder: `touch ~/.config/noctraos/no-update-check`.
- **Updates are signed and arrive in stages**, on the `stable` channel unless you choose `nightly`.
- **They can be undone.** If an update fails, the previous version is put back automatically. Later, **Go back to the previous update** on the Updates page (or `noc channel rollback`) restores the previous NoctraOS layer. Files that an update changed for a new feature stay changed, so a rollback undoes the code, not your data.
- **They never break the system on purpose.** Changes are additive first, and an update must keep your choices, such as Ollama staying off at startup.

## The terminal is optional, never forced

Everything the Control Panel does, `noc` does too, so nothing is lost if a window will not open. [Control Panel](control-panel.md) lists the command for each action, and every page has a quiet *Terminal* button with the same.

More on how updates work: [Updates](updates.md). What NoctraOS is for: [Objectives](objectives.md).
