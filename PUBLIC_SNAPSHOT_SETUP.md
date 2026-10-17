# Public source snapshot setup

This branch is a code snapshot, not a production-data backup. Runtime credentials, JSON data/configuration, CSV logs, bot persistence, and uploaded media are intentionally excluded. Keep those files in secure storage and restore or initialize them separately when deploying.

Configure required values through the deployment environment, never in source control: `BOT_TOKEN`, `SESSION_SECRET` (or `SECRET_KEY`), `ADMIN_EMAIL`, `ADMIN_ID`, `ADMIN_PASSWORD`, `VT_API_KEY`, `VT_PUBLIC_KEY`, `VT_SECRET_KEY`, and `REPL_SLUG` where needed.
