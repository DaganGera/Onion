#!/usr/bin/env bash
# Publish the landing page (site root) and the web app (./app/) to the gh-pages branch.
# Usage: npm run build && npm -w @parakh/landing run build && bash tools/deploy_pages.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
git -C "$ROOT" worktree prune
git -C "$ROOT" branch -D gh-pages-new >/dev/null 2>&1 || true
git -C "$ROOT" worktree add --force --detach "$TMP" >/dev/null
cd "$TMP"
git checkout --orphan gh-pages-new >/dev/null 2>&1
git rm -rfq . || true
cp -r "$ROOT/apps/landing/dist/." .
mkdir -p app
cp -r "$ROOT/apps/web/dist/." app/
cp "$ROOT/tools/pages/sw.js" sw.js
touch .nojekyll
git add -A
git commit -qm "Deploy SAMA landing + web app"
git push -f origin HEAD:gh-pages
cd "$ROOT"
git worktree remove --force "$TMP"
# Enable Pages from the gh-pages branch (no-op if already enabled).
TOKEN="$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill | sed -n 's/^password=//p')"
REPO="$(git -C "$ROOT" remote get-url origin | sed -E 's#.*github.com[/:]([^/]+/[^/.]+)(\.git)?#\1#')"
curl -s -o /dev/null -w "pages create: %{http_code}\n" -X POST -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$REPO/pages" -d '{"source":{"branch":"gh-pages","path":"/"}}'
curl -s -H "Authorization: Bearer $TOKEN" "https://api.github.com/repos/$REPO/pages" | grep -E '"html_url"|"status"' || true
