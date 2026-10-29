#!/bin/bash
set -e

# Commit
git commit -m "🛡️ Sentinel: Enforce bounded reads on network streams"

# PR Body
cat << 'PR_EOF' > pr_body.txt
💡 What: Added bounds checks on line and JSON header length reads for untrusted network streams.
🎯 Why: To prevent Denial of Service (DoS) attacks via unbounded reads when a stream maliciously lacks delimiters.
⚠️ Risk: Low, added length limits are very large (1MB) and well above normal payloads.
🔬 Verified: Tests and linter pass locally.
📎 Scope: `wakeword.py`, `wakeword_bench.py`
PR_EOF

# PR via GH CLI. I'm just leaving the gh pr create step here without git push since environment blocks it. We can commit with submit tool!
