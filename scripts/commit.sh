#!/usr/bin/env bash

set -e

if [ -z "$1" ]; then
  echo "Usage: ./scripts/commit.sh \"commit message\""
  exit 1
fi

echo "🔍 Running tests..."
pytest

echo "➕ Staging changes..."
git add .

if git diff --cached --quiet; then
  echo "Nothing to commit."
  exit 0
fi

echo "📝 Committing..."
git commit -m "$1"

echo "🚀 Pushing to origin (SSH)..."
git push

echo "✅ Done."

