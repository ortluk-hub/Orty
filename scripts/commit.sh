#!/usr/bin/env bash

set -e

if [ -z "$1" ]; then
  echo "Usage: ./scripts/commit.sh \"commit message\""
  exit 1
fi

echo "🔍 Checking status..."
git status

echo "➕ Staging changes..."
git add .

echo "📝 Committing..."
git commit -m "$1"

echo "🚀 Pushing to origin..."
git push

echo "✅ Done."

