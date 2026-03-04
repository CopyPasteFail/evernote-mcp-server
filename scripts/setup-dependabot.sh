#!/usr/bin/env bash
set -euo pipefail

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: GitHub CLI (gh) is required but not installed." >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Error: gh is not authenticated. Run: gh auth login" >&2
  exit 1
fi

repo_name_with_owner="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
owner_name="${repo_name_with_owner%%/*}"
repository_name="${repo_name_with_owner##*/}"

mkdir -p .github
cat > .github/dependabot.yml <<'DEPENDABOT'
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10
DEPENDABOT

echo "Wrote .github/dependabot.yml for ${repo_name_with_owner}."

if gh api --silent \
  -X PUT \
  -H "Accept: application/vnd.github+json" \
  "/repos/${owner_name}/${repository_name}/vulnerability-alerts"; then
  echo "Enabled vulnerability alerts."
else
  echo "Warning: failed to enable vulnerability alerts via API." >&2
  echo "You can enable them manually in GitHub:"
  echo "  Settings -> Security -> Code security and analysis -> Dependabot alerts"
fi

echo
echo "Next steps:"
echo "1. Commit and push .github/dependabot.yml"
echo "2. Confirm Dependabot security updates are enabled in repository settings"
