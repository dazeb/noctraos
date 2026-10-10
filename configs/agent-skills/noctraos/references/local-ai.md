# Local AI (Ollama, models, GPU)

Local AI is an **option**, never part of the first install, and no model is downloaded until the person asks (`tests/test_core_install.py` keeps it so).

## Set up

`noc llm setup` (or the AI models page, "Set up local AI...") runs `install/optional/local_llm.sh` from the root-owned snapshot: GPU stack (`noc-gpu`, **before** Ollama so Ollama sees the GPU), the Ollama engine and service, and LLMFIT (pipx). The panel shows a summary (Ollama about 1.4 GB, GPU driver lines, "no model is downloaded"), a free-disk check (`panel.LOCAL_AI_NEEDS` + GPU need) and asks for a yes first.

Why GPU first: Ollama's installer exits early only if `nvidia-smi` exists; otherwise it installs NVIDIA's DKMS `cuda-drivers` over the Ubuntu-signed driver.

## Ollama service

- Ollama's own installer enables `ollama.service` at boot. NoctraOS brackets it with `ollama_boot_choice` / `ollama_boot_restore` (`install/lib.sh`): a first install ends **off at boot but running now**; a re-run or Ollama update restores whatever the person had. Machines that already had it enabled keep it.
- `noc llm start|stop` control it now; `noc llm autostart on|off` controls boot. State is `systemctl is-enabled ollama.service` (no file of ours); `noc status --json` carries `ollama.autostart` (true/false/null when there is no unit).
- A stopped Ollama that is not set to start is **not** a failure: `noc doctor` shows `info`, the card says "Off", not "Not running". Newer systemd prints `not-found` (older prints nothing) from `is-enabled` for a missing unit: treat both as "no unit".

## Models

- `noc models list [--json]` (includes per-model `capabilities`), `presets` (sized to RAM/VRAM), `pull <model>`, `rm <model>`, `default [name]`.
- **One default model, one file.** `noc models default <name>` writes `~/.config/noctraos/model`. Precedence everywhere: `NOCTRAOS_MODEL`, then that file, then `qwen2.5-coder:7b`. The Welcome app, `noctraos-hermes`, "Ask AI to Explain", and the seeded Continue config (its `    model:` lines) each read it with the same few lines of inline lookup: change them together.
- `noc llm fit` runs LLMFIT to find a model that fits this machine.
- Embeddings for RAG: use Ollama's `/api/embed`, not `/api/embeddings`.

## GPU (`bin/noc-gpu`)

`noc gpu detect [--json] | install | status [--json]`. VERSION must match `noc`.

- NVIDIA: the **driver comes from Ubuntu** (`ubuntu-drivers`, signed, no DKMS); only the CUDA toolkit comes from NVIDIA's repo. The apt pin file `noctraos-cuda-toolkit-only` blocks that repo's driver packages - **never remove it** (mixed Ubuntu/NVIDIA `libnvidia-*` breaks the driver). It is written before the repo is registered and a failed write aborts. CUDA 13 dropped Maxwell/Pascal/Volta, which stay on driver 580 + CUDA 12.9. NVIDIA debs do not create `/usr/local/cuda`; `ensure_cuda_symlink` does.
- AMD: ROCm only when positively recognised; unknown AMD defaults to **Vulkan** (`OLLAMA_VULKAN=1`), never a ~15 GiB ROCm install. Polaris (RX 580) has no ROCm: Vulkan/RADV verified.
- GPU setup in the panel is **never automatic**: Hardware page shows what was found, then a consent dialog (what installs, rough size, restart/re-login needs, free-disk check), then `pkexec noc-privileged gpu-install <nvidia|amd|all>`. It never offers an install over a pending reboot or for a too-old NVIDIA card. Sizes in `panel.GPU_NEEDS` are estimates.
- Testing: VMs have no GPU, so they prove only "no GPU -> skip, idempotent". Real coverage is the unit tests (fixture lspci via `NOC_GPU_LSPCI_FILE`, `--dry-run`) plus a disposable `ubuntu:24.04` container for the AMD/apt path. `noc gpu install --dry-run` is safe on a dev box. A real AMD test VM exists on TrueNAS (see [development](development.md)); NVIDIA and ROCm are untested on real hardware.
