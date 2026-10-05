# Security policy

If you find a security problem in NoctraOS (the installer, the setup scripts, the
`noc` tools, the website, or a published image), please report it privately to
**admin@noctraos.dev** with *Security* in the subject, rather than opening a public issue.

Include what you found, how to reproduce it, the NoctraOS version
(`cat /etc/noctraos-release`), and anything you already tried. Please remove passwords
and personal data from logs.

We will acknowledge your report, keep you updated while we work on a fix, and tell you
when it is released. Please give us a reasonable chance to fix the problem before you
share the details publicly.

Known by design, not vulnerabilities: the downloadable VM disks are trial appliances that
sign in automatically as `noctraos` (password `noctraos`) with passwordless sudo, and are
labelled that way on the download page. Prompts sent to Hermes' free tier leave the
computer, as the README says.
