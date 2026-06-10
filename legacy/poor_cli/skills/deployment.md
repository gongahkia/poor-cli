---
description: Deployment and CI guidance
target: prompt
keywords:
  - deploy
  - deployment
  - release
  - publish
  - ship
  - production
  - ci
  - cd
  - github actions
  - workflow
  - pipeline
priority: 90
---
DEPLOYMENT TASK:
- Surface environment, rollback, and blast-radius concerns before shipping.
- Confirm production-impacting mutations before executing them.
- Verify result via the narrowest reliable signal available: logs, status checks, or smoke tests.
