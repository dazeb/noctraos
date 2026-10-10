# Base ISO scripts, one per flavour

One file per flavour, named by its id: `zorin.sh` and `kubuntu.sh`. Each defines its base ISO,
its installer, its boot chain and its rebrand steps. Build steps shared by every flavour stay in
`iso/`.

Rules:
- Only `zorin` and `kubuntu` are valid file names. `tests/test_flavour_layout.py` enforces this.
- Never add a flavour `if` inside `iso/build-noctraos-iso.sh`. Shared helpers only.
- Changes here need the code owner's review (`.github/CODEOWNERS`).

Status: empty. The Zorin remaster is still `iso/build-noctraos-iso.sh`, and it moves here in a
separate change. The Kubuntu build has not started.
