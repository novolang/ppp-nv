#!/usr/bin/env bash
# tests/coverage.sh — the measured line coverage over `src/`, merged
# across the suites.
#
# `novo test --cov` measures one suite file at a time, and a suite's
# percentage counts the suite's own lines as well as the package's.  No
# single number it prints is the one `docs/publishing.md`
# § Test coverage asks for.  This merges the per-suite LCOV and reports
# `src/` alone, which is what a release is measured on.  A line excused
# with a `// cov: skip — <reason>` marker directly above it is listed
# with its reason rather than counted as missing.
#
# Run from anywhere:  bash tests/coverage.sh
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG="$(cd "$HERE/.." && pwd)"
NOVO="${NOVO:-novo}"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/ppp-nv-cov.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

for suite in "$PKG"/tests/*_tests.nv; do
  base="$(basename "$suite" .nv)"
  ( cd "$PKG" && NOVO_LEAK_CHECK=0 timeout 1800 "$NOVO" test "tests/$base.nv" \
      --cov --report=lcov ) >"$WORK/$base.log" 2>&1
  if [ -f "$PKG/_novo/$base.lcov.info" ]; then
    cp "$PKG/_novo/$base.lcov.info" "$WORK/"
  else
    echo "  ✗ $base — no LCOV written; see $WORK/$base.log"
    exit 1
  fi
done

python3 - "$WORK" <<'PY'
import collections, glob, os, re, sys

work = sys.argv[1]
skip = re.compile(r'//\s*cov:\s*skip\s*[—-]+\s*(.*)')
cov = collections.defaultdict(dict)
for path in glob.glob(os.path.join(work, '*.lcov.info')):
    current = None
    for line in open(path):
        line = line.strip()
        if line.startswith('SF:'):
            current = line[3:]
        elif line.startswith('DA:'):
            n, hits = line[3:].split(',')[:2]
            n, hits = int(n), int(hits)
            cov[current][n] = cov[current].get(n, 0) + hits

def excuse(lines, n):
    i = n - 2
    while i >= 0 and (lines[i].strip().startswith('//') or not lines[i].strip()):
        m = skip.search(lines[i])
        if m:
            return m.group(1).strip()
        i -= 1
    return None

total = covered = 0
excused = []
print('')
for path in sorted(cov):
    if os.sep + 'src' + os.sep not in path:
        continue
    text = open(path).read().split('\n')
    lines = cov[path]
    missed = []
    for n, v in sorted(lines.items()):
        if v > 0:
            continue
        reason = excuse(text, n)
        if reason:
            excused.append((os.path.basename(path), n, reason))
        else:
            missed.append(n)
    hit = sum(1 for v in lines.values() if v > 0)
    total += len(lines)
    covered += hit
    print('  %-20s %4d/%-4d  %s' % (
        os.path.basename(path), hit, len(lines),
        'uncovered: ' + ' '.join(str(n) for n in missed) if missed else '100%'))
    for f, n, r in excused:
        print('    skip %s:%d — %s' % (f, n, r))
pct = 100.0 * covered / total if total else 0.0
print('')
print('  src/ total: %d/%d lines — %.1f%%, %d excused' % (covered, total, pct, len(excused)))
sys.exit(0 if covered + len(excused) == total else 1)
PY
