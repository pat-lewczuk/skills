# AGENTS.md

This repo publishes agent skills. Each skill lives in `skills/<name>/` and is consumed by
copying that directory into another project's `.claude/skills/`.

## Layout

```
skills/<name>/
  SKILL.md            required — YAML frontmatter (name, description) + body
  references/*.md     loaded on demand, not on every turn
  scripts/*.py        mechanical passes; run with python3, stdlib only
```

`name` in the frontmatter must match the directory name. `description` is always in context
for every skill installed — it states what the skill does *and* the trigger conditions, in
one dense sentence.

## Editing skills

This repo's own subject matter is context cost, so hold its files to the standard the
`eliminate-no-op` skill describes: a line earns its place by carrying a project-specific noun,
countering a model tendency, or describing a recovery path. Read
`skills/eliminate-no-op/references/taxonomy.md` before adding prose to any `SKILL.md`.

Put explanation in `references/`, not `SKILL.md`. `SKILL.md` says *when* to read a reference;
the reference holds the detail.

Scripts stay stdlib-only — there is no install step, so a skill that needs `pip install` is a
skill that silently fails in the consuming project.

## Verifying a script change

```bash
python3 skills/eliminate-no-op/scripts/analyze.py AGENTS.md --repo .
```

Run it against this repo's own `AGENTS.md` — it is the smallest real target available and
exercises the path-reference checks.
