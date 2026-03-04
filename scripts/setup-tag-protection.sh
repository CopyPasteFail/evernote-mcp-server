#!/usr/bin/env bash
set -euo pipefail

RULESET_NAME="Protect release tags"
TAG_PATTERN="v*"

print_ui_fallback() {
  cat <<'FALLBACK'
Manual fallback (GitHub UI):
1. Open repository Settings.
2. Go to Rules -> Rulesets.
3. Create a new ruleset targeting Tags.
4. Set name to "Protect release tags".
5. Add target pattern include: v*
6. Add a rule that restricts tag creation to maintainers/admins.
7. Save and verify contributors cannot create v* tags.
FALLBACK
}

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

echo "Configuring tag protection for ${repo_name_with_owner} (${TAG_PATTERN})..."

existing_ruleset_id="$(gh api "/repos/${owner_name}/${repository_name}/rulesets" --jq ".[] | select(.name == \"${RULESET_NAME}\") | .id" 2>/dev/null | head -n 1 || true)"

ruleset_payload_file="$(mktemp)"
trap 'rm -f "$ruleset_payload_file"' EXIT

cat > "$ruleset_payload_file" <<'JSON'
{
  "name": "Protect release tags",
  "target": "tag",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["v*"],
      "exclude": []
    }
  },
  "rules": [
    {
      "type": "creation"
    }
  ],
  "bypass_actors": [
    {
      "actor_type": "RepositoryRole",
      "actor_id": 5,
      "bypass_mode": "always"
    }
  ]
}
JSON

ruleset_success="false"
if [[ -n "$existing_ruleset_id" ]]; then
  if gh api \
    --silent \
    -X PUT \
    "/repos/${owner_name}/${repository_name}/rulesets/${existing_ruleset_id}" \
    --input "$ruleset_payload_file"; then
    ruleset_success="true"
    echo "Updated existing tag ruleset (${existing_ruleset_id})."
  fi
else
  if gh api \
    --silent \
    -X POST \
    "/repos/${owner_name}/${repository_name}/rulesets" \
    --input "$ruleset_payload_file"; then
    ruleset_success="true"
    echo "Created new tag ruleset."
  fi
fi

if [[ "$ruleset_success" == "true" ]]; then
  echo "Tag protection configured successfully."
  exit 0
fi

echo "Ruleset API attempt failed. Trying legacy tag-protection endpoint..." >&2
if gh api \
  --silent \
  -X POST \
  -H "Accept: application/vnd.github+json" \
  "/repos/${owner_name}/${repository_name}/tags/protection" \
  -f pattern="$TAG_PATTERN"; then
  echo "Legacy tag protection endpoint succeeded."
  exit 0
fi

echo "Failed to configure tag protection via API." >&2
print_ui_fallback
exit 1
