---
name: changelog
description: Draft a CHANGELOG entry from merged PRs since the last tag. Use when cutting a release or when the user asks what shipped.
---

# Changelog

- Range: `git log $(git describe --tags --abbrev=0)..HEAD --oneline`
- One bullet per user-visible change, grouped Added / Fixed / Changed.
- Skip anything with the `internal` label.
