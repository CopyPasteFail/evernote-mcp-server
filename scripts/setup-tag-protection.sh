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
5. Add target pattern include: v* (or refs/tags/v* if GitHub UI requires a fully-qualified ref pattern)
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

echo "Applying tag protection (best effort) for ${repo_name_with_owner} (${TAG_PATTERN})..."

existing_ruleset_id="$(gh api \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "/repos/${owner_name}/${repository_name}/rulesets" \
  --jq ".[] | select(.name == \"${RULESET_NAME}\") | .id" \
  2>/dev/null | head -n 1 || true)"

ruleset_payload_file="$(mktemp)"
ruleset_error_output_file="$(mktemp)"
trap 'rm -f "$ruleset_payload_file" "$ruleset_error_output_file"' EXIT

# RepositoryRole actor_id 5 allows repository admin/maintainer bypass for release-tag creation in this repo's release flow.
cat > "$ruleset_payload_file" <<'JSON'
{
  "name": "Protect release tags",
  "target": "tag",
  "enforcement": "active",
  "bypass_actors": [
    {
      "actor_type": "RepositoryRole",
      "actor_id": 5,
      "bypass_mode": "always"
    }
  ],
  "conditions": {
    "ref_name": {
      "include": ["refs/tags/v*"],
      "exclude": []
    }
  },
  "rules": [
    {
      "type": "creation"
    }
  ]
}
JSON

ruleset_success="false"
if [[ -n "$existing_ruleset_id" ]]; then
  : >"$ruleset_error_output_file"
  if gh api \
    -X PUT \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "/repos/${owner_name}/${repository_name}/rulesets/${existing_ruleset_id}" \
    --input "$ruleset_payload_file" \
    >/dev/null \
    2>"$ruleset_error_output_file"; then
    ruleset_success="true"
    echo "Updated existing tag ruleset (${existing_ruleset_id})."
  else
    echo "Rulesets API update failed for ruleset id ${existing_ruleset_id}." >&2
    if [[ -s "$ruleset_error_output_file" ]]; then
      echo "--- gh api error output ---" >&2
      cat "$ruleset_error_output_file" >&2
      echo >&2
    fi
  fi
else
  : >"$ruleset_error_output_file"
  if gh api \
    -X POST \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "/repos/${owner_name}/${repository_name}/rulesets" \
    --input "$ruleset_payload_file" \
    >/dev/null \
    2>"$ruleset_error_output_file"; then
    ruleset_success="true"
    echo "Created new tag ruleset."
  else
    echo "Rulesets API create failed." >&2
    if [[ -s "$ruleset_error_output_file" ]]; then
      echo "--- gh api error output ---" >&2
      cat "$ruleset_error_output_file" >&2
      echo >&2
    fi
  fi
fi

if [[ "$ruleset_success" == "true" ]]; then
  echo "Tag protection configured successfully via rulesets API."
  echo "Ruleset includes maintainer/admin bypass for release tag creation."
  exit 0
fi

echo "Automatic tag protection setup did not complete." >&2
echo "Note: GitHub rulesets API and payload shape can change over time." >&2
print_ui_fallback
exit 1
