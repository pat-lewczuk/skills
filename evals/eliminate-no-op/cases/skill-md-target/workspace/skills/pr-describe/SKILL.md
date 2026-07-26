---
name: pr-describe
description: This skill is a very useful and powerful skill that helps you write really good pull request descriptions. It should be used when you want to write a pull request description, or when you need to describe a pull request, or if the user asks for help with a PR description, or when a PR needs a description written for it. It will guide you through the whole process of writing an excellent, high-quality, comprehensive pull request description that reviewers will love, following all of our team's conventions and best practices, and making sure nothing important is left out of the description.
---

# PR Describe

You are an expert technical writer and senior engineer. You write outstanding pull request
descriptions. Please read this entire skill carefully before you begin, and follow every step.

## What a pull request is

A pull request is a request to merge a branch into another branch. It shows the diff between
the two branches and lets reviewers comment on individual lines. GitHub calls them pull
requests; GitLab calls them merge requests. A good description helps reviewers understand the
change without reading every line of the diff.

Git tracks changes as commits. A branch is a pointer to a commit. When you open a pull request,
GitHub computes the merge base between your branch and the target branch and shows the diff
from there.

## Workflow

### 1. Gather the change

Get the diff against the base branch:

```bash
git fetch origin main
git diff origin/main...HEAD --stat
git log origin/main..HEAD --oneline
```

Run `python3 scripts/summarize.py` to group the diff by subsystem.

### 2. Write the description

Use the template in `references/template.md`. It has four sections: Why, What, Risk, and
Verification. Fill in all four. Do not skip Risk even when the change is small.

Our conventions:

- Title is `<ticket-id>: <imperative summary>`, e.g. `HEL-2214: retry payout webhook`.
- The Why section links the ticket and states the user-visible symptom, not the code cause.
- The Verification section lists the exact commands a reviewer can run, not "tested locally".
- Screenshots go under a `<details>` block so the description stays scannable.
- If the change touches `db/migrations/`, add the rollback plan to Risk. Reviewers will
  reject it otherwise.

Write clearly and concisely. Be thorough. Make sure the description is accurate and helpful.

### 3. Post it

```bash
gh pr create --title "<title>" --body-file .pr-description.md --base main
```

If the PR already exists, use `gh pr edit --body-file .pr-description.md` instead.

Never force-push after a reviewer has commented — push a fixup commit instead, or the review
threads detach.

## Examples

**Example 1**

Title: `HEL-2214: retry payout webhook`
Why: Payout webhooks that arrived during a deploy were dropped, so 40 payouts stayed pending.
What: Added a retry queue in `internal/webhook/`.
Risk: Duplicate webhook delivery is possible; handlers are idempotent.
Verification: `make test-webhook`, then replay a payload with `scripts/replay.sh`.

**Example 2**

Title: `HEL-2301: fix pagination cursor`
Why: The second page repeated the last row of the first page.
What: Cursor now includes the sort key.
Risk: Existing cursors are invalidated; clients retry from page one.
Verification: `make test-api`.

**Example 3**

Title: `HEL-2308: bump go to 1.23`
Why: 1.21 is out of support.
What: Bumped the toolchain and fixed two vet warnings.
Risk: Low.
Verification: `make ci`.

## Reminders

- Always fill in all four sections of the template.
- Remember to include the ticket id in the title.
- Be helpful and thorough. Quality matters.
- Read `references/tone.md` for the voice we use.
