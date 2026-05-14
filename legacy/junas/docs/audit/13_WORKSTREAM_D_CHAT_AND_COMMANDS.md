# Workstream D: Chat, Command System, and Interaction Integrity

Owner goal: make chat/command UX reliable and aligned with actual capabilities.

## Owned Write Scope
- `frontend/app/chat/page.tsx`
- `frontend/components/chat/CommandPalette.tsx`
- `frontend/components/chat/CommandSuggestions.tsx`
- `frontend/lib/commands/command-handler.ts`
- `frontend/lib/use-keyboard-shortcuts.ts`
- `frontend/components/chat/ConversationHistory.tsx`
- `frontend/lib/conversation-store.ts`

## Do Not Edit
- `frontend/components/side-nav.tsx`
- Backend APIs

## Tasks
1. Introduce one capability registry used by:
   - slash suggestions
   - command palette
   - command handler dispatch
2. Remove or implement currently advertised but unsupported commands.
3. Fix route mapping bug for Home navigation in command palette.
4. Harden chat edit/branch flow:
   - remove stale-state timing hazards around `saveEdit` and `sendMessage`
   - ensure no duplicate user message insertion.
5. Standardize keyboard handling:
   - bounded suggestion selection index
   - avoid hidden key collisions.

## Acceptance Criteria
- Every visible command is executable or intentionally disabled with explanation.
- No dead navigation targets from command palette.
- Chat edit-to-branch behavior is deterministic.
- Command interactions have clear error feedback.

## Validation
- Manual command smoke test for each listed command.
- Branch/edit regression checks in chat thread.

