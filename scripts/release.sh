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

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Error: working tree is not clean. Commit or stash changes before releasing." >&2
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
  echo "Error: tag $new_release_tag already exists." >&2
  exit 1
fi

git tag -a "$new_release_tag" -m "Release $new_release_tag"
git push origin "$new_release_tag"

echo "Created and pushed tag $new_release_tag"
