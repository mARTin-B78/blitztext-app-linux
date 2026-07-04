git push -u origin HEAD
gh pr create --title "🛡️ Sentinel: Enforce Wyoming protocol length bounds to prevent DoS" --body "💡 What
Add limits to JSON parsing and binary payload reading.

🎯 Why
Prevent DoS via unbounded memory allocation.

⚠️ Risk
None.

🔬 Verified
Ran bench tests.

📎 Scope
linux/blitztext/wakeword.py, linux/blitztext/wakeword_bench.py"
