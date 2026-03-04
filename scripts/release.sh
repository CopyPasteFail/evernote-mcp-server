#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/release.sh {patch|minor|major}

Examples:
  ./scripts/release.sh patch
  ./scripts/release.sh minor
  ./scripts/release.sh major
USAGE
}

print_tag_creation_restricted_message() {
  local release_tag="$1"
  cat >&2 <<EOF
Error: remote rejected tag '$release_tag' because tag creation is restricted by repository rules.

Next steps:
1. Open repository Settings -> Rules -> Rulesets.
2. Edit the tag ruleset that matches refs/tags/v*.
3. Add a bypass actor for the maintainer identity that runs releases (user/team/app), or relax the creation restriction.
4. Re-run: ./scripts/release.sh {patch|minor|major}
EOF
}

if [[ $# -ne 1 ]]; then
  if [[ $# -eq 0 ]]; then
    echo "Error: missing version bump type." >&2
  else
    echo "Error: expected exactly one version bump type argument." >&2
  fi
  echo >&2
  usage >&2
  exit 1
fi

version_bump_type="$1"
if [[ "$version_bump_type" != "patch" && "$version_bump_type" != "minor" && "$version_bump_type" != "major" ]]; then
  echo "Error: invalid version bump type '$version_bump_type'." >&2
  echo "Valid options: patch, minor, major." >&2
  echo >&2
  usage >&2
  exit 1
fi

if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  echo "Error: working tree is not clean. Commit, stash, or remove changes before releasing." >&2
  exit 1
fi

current_branch_name="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$current_branch_name" != "main" ]]; then
  echo "Error: releases must be created from main. Current branch: $current_branch_name" >&2
  exit 1
fi

git fetch origin main --tags

local_head_commit="$(git rev-parse HEAD)"
remote_main_commit="$(git rev-parse origin/main)"
if [[ "$local_head_commit" != "$remote_main_commit" ]]; then
  echo "Error: HEAD does not match origin/main. Pull/push main first." >&2
  exit 1
fi

make check

latest_release_tag="$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | head -n 1)"
if [[ -z "$latest_release_tag" ]]; then
  latest_release_tag="v0.0.0"
fi

version_without_prefix="${latest_release_tag#v}"
IFS='.' read -r major_version minor_version patch_version <<< "$version_without_prefix"

case "$version_bump_type" in
  patch)
    patch_version=$((patch_version + 1))
    ;;
  minor)
    minor_version=$((minor_version + 1))
    patch_version=0
    ;;
  major)
    major_version=$((major_version + 1))
    minor_version=0
    patch_version=0
    ;;
esac

new_release_tag="v${major_version}.${minor_version}.${patch_version}"

if git rev-parse -q --verify "refs/tags/$new_release_tag" >/dev/null; then
  echo "Error: local tag $new_release_tag already exists." >&2
  echo "If this is from a previous failed push, remove it with: git tag -d $new_release_tag" >&2
  exit 1
fi

git tag -a "$new_release_tag" -m "Release $new_release_tag"

push_error_output_file="$(mktemp)"
trap 'rm -f "$push_error_output_file"' EXIT
if ! git push origin "$new_release_tag" 2>"$push_error_output_file"; then
  push_error_output="$(cat "$push_error_output_file")"
  if grep -q "GH013" "$push_error_output_file" && grep -q "creations being restricted" "$push_error_output_file"; then
    git tag -d "$new_release_tag" >/dev/null
    print_tag_creation_restricted_message "$new_release_tag"
    exit 1
  fi

  echo "$push_error_output" >&2
  echo "Error: failed to push tag $new_release_tag. Local tag has been removed to avoid partial release state." >&2
  git tag -d "$new_release_tag" >/dev/null
  exit 1
fi

echo "Created and pushed tag $new_release_tag"
