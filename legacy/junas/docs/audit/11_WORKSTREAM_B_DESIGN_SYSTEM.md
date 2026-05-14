# Workstream B: Design System and UI Consistency

Owner goal: reduce inline-style sprawl and establish reusable UI primitives.

## Owned Write Scope
- `frontend/app/globals.css`
- `frontend/components/ui/**` (new)
- `frontend/components/theme-toggle.tsx`
- `frontend/lib/theme-provider.tsx`

## Do Not Edit
- Feature page business logic (`frontend/app/**/page.tsx`)
- Backend files

## Tasks
1. Introduce reusable UI primitives:
   - `Button`, `Input`, `Textarea`, `Select`, `Card`, `Badge`, `Tabs`, `StatusBanner`.
2. Standardize semantic class usage in CSS:
   - form controls
   - action states (loading/error/success)
   - panel layout primitives
3. Replace ad-hoc theme script assumptions with safer hydration-friendly theme init behavior.
4. Add accessibility defaults:
   - focus styles
   - contrast checks for badge/status classes
   - reduced-motion friendly transitions

## Acceptance Criteria
- Inline style count drops materially from baseline (194).
- New UI primitives are consumable by other workstreams.
- Theme switching remains functional and SSR-safe.
- No visual regressions in core shell and chat view.

## Validation
- Run frontend build/lint if available.
- Spot-check dark/light mode across workspace + 3 legacy pages.

