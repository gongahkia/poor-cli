---
description: Batch file reads when possible
target: system
contexts:
  - batched_reads
priority: 40
---
EFFICIENCY: When you need to read multiple files, batch them into a single tool call round. Avoid serial one-file-per-iteration reads when one grouped read will do.
