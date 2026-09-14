#!/usr/bin/env bash
# The whole verification block. Exits non-zero if any check fails.
#
#   scripts/verify.sh [--quick]
#
# --quick skips the two browser-driven checks and the determinism check. Use it
# while iterating; never use it as the gate for a cycle.
#
# Deliberately does NOT stop at the first failure: one broken thing usually
# breaks several checks, and seeing all of them at once says which is the cause.
set -u

ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
cd "$ROOT"

QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1

FAILED=()
run () {                       # run <name> <command...>
  local name="$1"; shift
  printf '\n== %s\n' "$name"
  if "$@"; then
    printf '   PASS  %s\n' "$name"
  else
    printf '   FAIL  %s\n' "$name"
    FAILED+=("$name")
  fi
}

# The unit suite. pytest.ini scopes discovery to analysis/tests and
# executive_dashboard/tests.
run "pytest" python3 -m pytest -q

# The same suite with polars stubbed out. CI installs only `flake8 pytest`, so a
# polars import at module scope passes here and breaks there — which has already
# happened once and cost a commit to fix.
run "pytest without polars (as CI sees it)" \
  python3 -c "import sys; sys.modules['polars']=None; import pytest; sys.exit(pytest.main(['-q','analysis/tests']))"

run "node unit tests" node --test mobile/tests/mobile.test.js

if [ "$QUICK" = 0 ]; then
  # Boots the built bundle in Chromium over file:// and walks every section.
  # A section that vanishes from the registry, renders empty, or throws fails.
  run "mobile smoke test" python3 mobile/tools/smoke_test.py

  # Opens the generated workbook with openpyxl, parses the CSV and the SVG and
  # decodes the PNG. The XLSX writer is hand-rolled, so it is proved not assumed.
  run "export checks" python3 mobile/tools/test_exports.py

  # Drives the ad-hoc builder and reconciles the total it shows against the
  # same figure computed a second way from the payload. The engine has unit
  # tests; this is the half they cannot cover — that the controls are wired to
  # it and that a drill-down still adds up to the row it was opened from.
  run "ad-hoc reporting" python3 mobile/tools/test_adhoc.py

  # The build must be deterministic, or "nothing changed" cannot be told apart
  # from "changed and changed back".
  printf '\n== deterministic build\n'
  hashes=$(for _ in 1 2 3; do
             python3 mobile/build_standalone.py >/dev/null
             sha256sum mobile/dist/Abu_Hashem_Mobile_standalone.html | cut -d' ' -f1
           done | sort -u | wc -l)
  if [ "$hashes" = "1" ]; then
    printf '   PASS  three builds, one hash\n'
  else
    printf '   FAIL  three builds produced %s different hashes\n' "$hashes"
    FAILED+=("deterministic build")
  fi
fi

run "flake8 (syntax and undefined names)" \
  python3 -m flake8 . --count --select=E9,F63,F7,F82

printf '\n────────────────────────────\n'
if [ "${#FAILED[@]}" -eq 0 ]; then
  [ "$QUICK" = 1 ] && printf 'quick checks passed — run without --quick before shipping\n' \
                   || printf 'all checks passed\n'
  exit 0
fi
printf 'FAILED: %s\n' "${FAILED[*]}"
printf 'The cycle is not finished. Fix these before documenting or pushing.\n'
exit 1
