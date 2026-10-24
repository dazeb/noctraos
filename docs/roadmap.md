# Public roadmap

This roadmap lists the next outcomes for NoctraOS. It is not a release calendar. [Objectives](objectives.md) defines the product direction, and the [release runbook](release-runbook.md) records release gates and evidence.

## Current baseline

NoctraOS 0.5.0 ships as two flavours. The `zorin` flavour on Zorin OS 18.1 with GNOME is the recommended download. The `kubuntu` flavour on Kubuntu 26.04 with KDE Plasma is a preview.

The public repository contains the installer, the Control Panel, Super+Space search, signed updates, release tooling and the website. Local AI is optional. No model is downloaded until the user chooses one.

## Near-term priorities

| Priority | Outcome | Completion evidence |
| --- | --- | --- |
| Choice and component control | Every non-core component can be installed, disabled or removed from the Control Panel and with `noc`. Each action explains its purpose and effects before it runs. | A component inventory identifies every default and optional item. Install, remove and reinstall tests pass, skipped choices remain respected, and the Control Panel and `noc` provide the same actions. |
| Plasma parity | The `kubuntu` flavour has Super+Space search, an AI-first Start layout and the remaining NoctraOS desktop integration. | A clean Kubuntu VM install passes `noc doctor`, the desktop acceptance checklist and an idempotent setup rerun. The published release notes state any remaining differences. |
| Installer and hardware coverage | Both flavours have more evidence beyond the build VM, including interactive installation and supported NVIDIA and AMD paths. | Test reports name the exact image, hardware or hypervisor, result and untested boundaries. A failed path remains a known limitation until it passes. |
| Safe updates on both flavours | Signed, staged NoctraOS updates preserve user choices and can roll back on each supported flavour. | The update, migration and rollback tests pass for each flavour. Public channel checks confirm the expected manifest and bundle. |
| Onboarding and accessibility | First login explains Super+Space, cloud and local AI, privacy choices and optional setup without requiring a terminal. | Keyboard, scaling and screen-reader checks cover the welcome, search and Control Panel. A fresh-install walkthrough confirms the wording and flow. |
| Contributor path | A new contributor can find a bounded task, run the relevant checks and understand the affected part of the system. | The issue tracker has scoped starter work. The contributor guide, architecture notes and test commands match the current repository. |

## Funding and accountability

NoctraOS is currently developed and maintained by one person. The project has no external investors or announced grant funding.

If funding is awarded, this page will record:

- the funder and funding period;
- the work covered by the award;
- the public deliverables and their licences;
- the evidence that shows whether each deliverable is complete.

Applying for funding does not change the roadmap or imply support from the organisation considering the application.

## How priorities are chosen

User safety and a working end-to-end path come first. New desktop work must account for both flavours, with separate acceptance evidence. NoctraOS tests system changes in a virtual machine before treating them as ready for a physical computer.
