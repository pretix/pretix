# PR Self-Review — UI Test: Event Creation

## What changed and why?
Added UI test for event creation flow to protect against regressions.

## Why is this the right test layer?
UI test verifies end-to-end event creation behavior from the user's perspective.

## What could still break?
UI selector changes could break tests if the frontend is updated.

## Risks or follow-ups?
- Need to add edge cases (invalid inputs, duplicate events)
- Could add more assertions on the created event details
