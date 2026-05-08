# Rizara Codex Safety Rules

You are working on the Rizara repo.

Do not run destructive database commands.

Do not run:
- flask db upgrade
- flask db downgrade
- flask db migrate
- psql write/delete/update/drop commands
- seed scripts
- create_admin.py
- git push
- git commit
- git reset --hard
- git clean -fd
- rm -rf

Unless I explicitly approve the exact command first.

Preferred workflow:
1. Inspect files.
2. Propose a small PR scope.
3. Make file changes only.
4. Run safe checks:
   - python -m compileall app scripts tests
   - pytest -q
   - python scripts/report_duplicate_routes.py
5. Stop and summarize.
6. Do not commit unless I explicitly say: "commit these changes".

Use a feature branch for every task.

Never connect to production database.
Never use production environment variables.
Never modify Render production configuration unless explicitly instructed.
