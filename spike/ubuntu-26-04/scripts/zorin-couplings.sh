#!/usr/bin/env bash
# Inventory every Zorin-specific reference in the product tree (not docs, not tests).
# Output: out/zorin-couplings.tsv (file, line, token, text) and a per-file count.
set -Eeuo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="$HERE/out/zorin-couplings.tsv"
mkdir -p "$HERE/out"
cd "$REPO"
printf 'file\tline\ttoken\ttext\n' > "$OUT"
grep -rniE 'zorin' install bin extensions branding configs scripts iso control search migrations assets/icons 2>/dev/null \
  | grep -viE 'Zorin OS 18\.1 \(Ubuntu|NoctraOS' \
  | while IFS=: read -r file line rest; do
      token="$(printf '%s' "$rest" | grep -oiE 'zorin[a-z0-9_.-]*' | head -1)"
      text="$(printf '%s' "$rest" | sed 's/^[[:space:]]*//' | cut -c1-160)"
      printf '%s\t%s\t%s\t%s\n' "$file" "$line" "${token:-zorin}" "$text"
    done >> "$OUT"
echo "total Zorin references: $(($(wc -l < "$OUT") - 1))"
echo "per file:"
tail -n +2 "$OUT" | cut -f1 | sort | uniq -c | sort -rn
