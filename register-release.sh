#!/bin/bash
set -e
FUNCTION_ID="$1"
FUNCTION_TOKEN="$2"

if [ -z "$FUNCTION_ID" ] || [ -z "$FUNCTION_TOKEN" ]; then
  echo "Usage: ./register-release.sh <FUNCTION_ID> <FUNCTION_TOKEN>"
  exit 1
fi

COMMIT_SHA=$(git rev-parse HEAD)
REPO=$(git config --get remote.origin.url | sed -E 's#.*github.com[:/]##; s#\.git$##')
ENGINE_URL="http://localhost:7071"
IMAGE="ghcr.io/${REPO}:${COMMIT_SHA}"

echo "Registering release for commit: $COMMIT_SHA"
echo "Image: $IMAGE"

curl -s -X POST "${ENGINE_URL}/api/v2/functions/${FUNCTION_ID}/releases" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${FUNCTION_TOKEN}" \
  -d "{\"versionTag\": \"${COMMIT_SHA}\", \"commitId\": \"${COMMIT_SHA}\", \"image\": \"${IMAGE}\", \"inputSchema\": {\"type\": \"object\", \"properties\": {}}}"

echo ""
echo "Done."
