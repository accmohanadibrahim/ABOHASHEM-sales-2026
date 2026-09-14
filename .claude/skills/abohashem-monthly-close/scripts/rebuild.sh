#!/usr/bin/env bash
# Rebuild everything, in the one order that produces a coherent set of outputs.
#
#   scripts/rebuild.sh [--deps]
#
# --deps also installs the pinned requirements first. Skipped by default because
# it is slow and usually already done; install them on a fresh checkout or when
# an import fails.
#
# WHY set -e MATTERS HERE, AND WHY README.md INSISTS ON IT
# Without it an early script fails, its OLD outputs stay on disk, the later
# scripts read a mix of new and stale data, the dashboards build cleanly from
# that mix, and the run reports success. The failure is invisible precisely
# because every step after the broken one works.
#
# Run this from anywhere inside the repo; it locates the root itself.
set -eu

ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
cd "$ROOT"

if [ "${1:-}" = "--deps" ]; then
  # Pinned on purpose. A newer statsmodels than 0.14.6 shifts the VIF
  # diagnostics, so every rebuild then looks like a data change when the data
  # did not change.
  python3 -m pip install -r analysis/requirements.txt
  python3 -m pip install -r executive_dashboard/requirements.txt
fi

echo "== analysis pipeline =="
# Numeric order is the dependency order. The tail matters most: 10 writes the
# dashboard payload, 13 joins cost to sales, 14 absorbs the income statements —
# and 13/14 write the profitability and expense outputs the mobile app reads.
# Stopping at 10 leaves the dashboard complete and those sections empty.
for f in analysis/0*.py analysis/1*.py; do
  echo "-- $f"
  python3 "$f"
done

echo "== executive dashboard =="
# build.py runs its own hard checks and exits non-zero on a failed one, so a bad
# rebuild stops here rather than reaching the app.
python3 executive_dashboard/build.py

echo "== mobile standalone =="
python3 mobile/build_standalone.py

echo
echo "rebuild OK — now run scripts/verify.sh"
