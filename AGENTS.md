# Repository instructions

For every frontend, Telegram UI, UX copy, or visual artifact task, read `PRODUCT.md`, `DESIGN.md`, and `docs/FRONTEND_RULES.md` completely before editing. Treat them as a mandatory contract.

Reuse the primitives in `frontend/src/components/ui` and `app/telegram/ui.py`. Do not create one-off buttons, cards, fields, badges, notices, skeletons, or Telegram keyboards inside feature code. When the contract changes, update `DESIGN.md` in the same change.

Never use interface text smaller than 13px. Keep body and form text at 16px, touch targets at least 44px, and avoid duplicated copy.

## Required Git workflow

After every completed implementation task:

1. Run the relevant tests and linters.
2. Review `git status` and the staged diff. Stage only files belonging to the task.
3. Never commit `.env`, Telegram sessions, credentials, database files, generated exports, logs, or temporary files.
4. Create a focused Conventional Commit describing the completed outcome.
5. Push the commit to the configured GitHub remote before reporting the task complete.

Do not combine unrelated pre-existing user changes into a task commit. If the worktree already contains mixed changes that cannot be separated safely, stop and ask whether to create an explicit checkpoint commit.

Deploy only a commit that has already been pushed. After production verification, create and push an annotated tag named `prod-YYYYMMDD-HHMM-<short-slug>` pointing to the deployed commit. Record database migrations and external infrastructure changes in the handoff because Git rollback does not revert data or VPS configuration.
