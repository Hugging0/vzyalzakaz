# GitHub, commits and rollback

## Repository setup

The project uses one private GitHub repository with `main` as the stable branch and `origin` as the remote name. Create the GitHub repository empty: do not initialize it with a README, `.gitignore`, or license because the local repository already has history.

Authentication must use GitHub CLI browser login or a dedicated SSH key. Do not put a GitHub token in `.env`, a shell command, project files, or chat history.

## Completed-task checklist

Every completed change follows this sequence:

```text
implementation
  → relevant tests and linters
  → review unstaged diff
  → stage task files only
  → review staged diff
  → focused Conventional Commit
  → push to GitHub
  → deploy the pushed commit
  → production health and functional check
  → annotated production tag and tag push
```

A task is not considered complete until its commit is pushed. Partial, broken, or unverified work is not committed as a normal feature commit. If a temporary recovery point is genuinely needed, label it explicitly as `chore: checkpoint ...`.

## Commit scope

Prefer one commit per independently reversible outcome. Use Conventional Commit prefixes:

- `feat:` — user-visible capability;
- `fix:` — defect correction;
- `refactor:` — behavior-preserving code improvement;
- `docs:` — documentation only;
- `test:` — tests only;
- `chore:` — build, dependency, deployment, or checkpoint work.

Never silently include unrelated files already modified by the user or another task.

## Secrets and generated data

The following must remain outside Git:

- `.env` and environment-specific variants;
- Telegram `.session` files;
- passwords, API keys, tokens and proxy credentials;
- PostgreSQL/SQLite data and backups;
- `output/`, `tmp/`, logs, caches and generated screenshots/exports.

`.env.example` contains names and safe placeholders only.

## Production tags

After a pushed commit is successfully verified in production, create an annotated tag:

```text
prod-YYYYMMDD-HHMM-short-slug
```

The tag identifies the exact code version deployed. External state must be recorded separately:

- database migration revision;
- required environment variables without their values;
- Docker image or compose change;
- Nginx/systemd configuration;
- external services such as the private SOCKS5 VPS.

## Rollback boundary

Checking out a production tag restores repository code only. It does not automatically reverse database migrations, delete collected data, restore `.env`, or revert another VPS. Before a risky migration, make a database backup and document a tested downgrade or forward-fix procedure.
