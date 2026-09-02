#!/usr/bin/env bash
set -euo pipefail

gh api --paginate \
  -X GET /user/repos \
  -f affiliation=owner,collaborator,organization_member \
  -f per_page=100 \
  --jq '.[].ssh_url' | sort -u
