#!/usr/bin/env bash
# Put the NoctraOS skill into ~/.agents/skills for accounts made before it existed (and for accounts other than the one that
# ran the installer), linked for Hermes and Claude Code where those are installed. Runs once per account; `noc agent-skills`
# does the real work and keeps what the person edited or switched off. A fresh install does this in module 07 and 11.
set -u
TOOL="${NOCTRAOS_AGENT_SKILLS_TOOL:-/usr/local/bin/noc-agent-skills}"
[ -x "$TOOL" ] || { echo "noc-agent-skills is not installed yet; retrying later" >&2; exit 1; }
"$TOOL" install
