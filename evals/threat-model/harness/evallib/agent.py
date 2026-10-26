"""Run a case through `claude -p` and read back what happened.

Everything the graders need is derived from the stream-json transcript: which skill fired,
which files were read, which tools ran, cost, turn count. The transcript stays on disk so a
surprising score can be traced to the actual run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def run_agent(sandbox: Path, prompt: str, out_dir: Path, *, model: str = "opus",
              max_usd: float = 2.0, timeout: int = 1800, tools: list | None = None,
              skill_name: str = "", extra_args: list | None = None) -> dict:
    """Invoke Claude Code headlessly inside `sandbox`. Returns run metadata."""
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose",
        "--model", model,
        "--permission-mode", "bypassPermissions",
        "--setting-sources", "project",
        "--no-session-persistence",
        "--max-budget-usd", str(max_usd),
        "--disallowed-tools", "WebSearch,WebFetch",
    ]
    if tools:
        cmd += ["--tools", ",".join(tools)]
    if extra_args:
        cmd += extra_args

    env = dict(os.environ)
    env.pop("CLAUDE_CODE_SSE_PORT", None)
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"

    out_dir.mkdir(parents=True, exist_ok=True)
    transcript = out_dir / "transcript.jsonl"
    stderr_path = out_dir / "stderr.log"

    with transcript.open("w", encoding="utf-8") as tf, \
            stderr_path.open("w", encoding="utf-8") as ef:
        try:
            proc = subprocess.run(cmd, cwd=str(sandbox), stdout=tf, stderr=ef,
                                  timeout=timeout, env=env, check=False)
            rc, timed_out = proc.returncode, False
        except subprocess.TimeoutExpired:
            rc, timed_out = -1, True

    meta = parse_transcript(transcript, skill_name)
    meta.update({"returncode": rc, "timed_out": timed_out,
                 "stderr_tail": stderr_path.read_text(encoding="utf-8",
                                                      errors="replace")[-1500:]})
    return meta


def parse_transcript(path: Path, skill_name: str = "") -> dict:
    tool_calls: list = []
    final_text = ""
    cost = turns = None
    if not path.exists():
        return {"tool_calls": [], "tool_names": [], "final_text": "", "triggered": False}

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for block in (ev.get("message", {}) or {}).get("content", []) or []:
                if block.get("type") == "tool_use":
                    tool_calls.append({"name": block.get("name"),
                                       "input": _shrink(block.get("input") or {})})
        elif ev.get("type") == "result":
            final_text = ev.get("result") or final_text
            cost = ev.get("total_cost_usd", cost)
            turns = ev.get("num_turns", turns)

    triggered = False
    if skill_name:
        for c in tool_calls:
            blob = json.dumps(c["input"])
            if c["name"] == "Skill" and skill_name in blob:
                triggered = True
            elif skill_name in blob and "SKILL.md" in blob:
                triggered = True

    return {
        "tool_calls": tool_calls,
        "tool_names": sorted({c["name"] for c in tool_calls if c["name"]}),
        "final_text": final_text[-6000:],
        "cost_usd": cost,
        "num_turns": turns,
        "triggered": triggered,
    }


def _shrink(inp: dict) -> dict:
    out = {}
    for k, v in inp.items():
        if isinstance(v, str):
            out[k] = v[:400]
        elif isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
        else:
            out[k] = json.dumps(v)[:400]
    return out


def install_skill(skill_dir: Path, sandbox: Path) -> None:
    """Copy the skill under test into the sandbox as a project skill."""
    dest = sandbox / ".claude" / "skills" / skill_dir.name
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill_dir, dest,
                    ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc"))


def structured_call(prompt: str, schema: dict, *, model: str = "opus",
                    cwd: Path | None = None, max_usd: float = 0.6,
                    timeout: int = 600) -> dict | None:
    """One-shot model call with schema-validated output. Used by the rubric judge."""
    cmd = ["claude", "-p", prompt, "--output-format", "json",
           "--json-schema", json.dumps(schema), "--model", model,
           "--tools", "", "--no-session-persistence", "--setting-sources", "project",
           "--max-budget-usd", str(max_usd)]
    try:
        proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                              text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0 and not proc.stdout.strip():
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    result = payload.get("result", payload)
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return None
    return result
