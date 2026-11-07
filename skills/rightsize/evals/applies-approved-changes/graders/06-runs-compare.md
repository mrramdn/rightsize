---
type: regex
target: trace
pattern: 'Before (?:→|\?|\\u2192) after  \(snapshot taken 20\d\d-\d\d-\d\dT[^)]*\)(?:\\n|\r?\n) {2}every session {2}~([\d,]+) (?:→|\?|\\u2192) ~(?!\1 )[\d,]+ tokens|snapshot_at\\?["'']: ?\\?["'']20\d\d-\d\d-\d\dT[^"''\\]*\\?["''],(?:\\n|\s)*\\?["'']before\\?["'']: ?\{(?:\\n|\s)*\\?["'']always_tokens\\?["'']: ?(\d+),[\s\S]{0,400}?\\?["'']after\\?["'']: ?\{(?:\\n|\s)*\\?["'']always_tokens\\?["'']: ?(?!\2,)\d+,'
weight: 1
arm: with-only
---

The run measured the result with the scanner's --compare, and the comparison worked. The pattern matches only what a
successful --compare prints, as it appears in the trace (JSON lines, so a line break is \n and a quote is \"): the
table's "Before → after  (snapshot taken <time>)" line followed by "every session  ~X → ~Y tokens", or the compare
object's snapshot_at followed by before and after always_tokens, raw --json output or re-printed by jq, json.dumps
or as a Python dict. The after figure must differ from the before figure, so a snapshot saved after the edits
doesn't count. A --compare that failed ("rightsize: error: no snapshot of ... yet") or a read of scan.py doesn't
match. The pattern follows render_table() and compare() in scripts/scan.py; update it when their output changes.

Indicator only (arm: with-only), not part of the score. In the eval sandbox no file outside the repo survives from
one Bash command to the next: $TMPDIR is read-only, /tmp is private to each command, and writes into .git/ are
refused. So --save has nowhere to keep its snapshot, and --compare can't succeed in either version.
