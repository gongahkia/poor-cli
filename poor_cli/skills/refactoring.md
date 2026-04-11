---
description: Behavior-preserving refactor guidance
target: prompt
keywords:
  - refactor
  - cleanup
  - simplify
  - restructure
  - rename
  - extract method
  - extract function
priority: 100
---
REFACTOR TASK:
- Preserve behavior exactly unless the user asks for semantic change.
- Keep the diff local to the stated target.
- Prefer smaller structural improvements over wholesale rewrites.
