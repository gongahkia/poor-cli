---
description: Read-only sandbox rules
target: system
contexts:
  - read_only
priority: 20
---
READ-ONLY MODE:
- Restrict work to reading, searching, diffing, and explanation.
- Do not attempt edits, writes, deletes, commits, or deploys.
- Surface the exact mutation you would make when blocked by sandbox limits.
