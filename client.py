"""Trip-planner service client (ported from the original server-side planner client).

Talks to any chat-completions compatible endpoint and returns parsed JSON.
Env (all three required): PLANNER_API_KEY, PLANNER_BASE_URL, PLANNER_MODEL.
"""
import json
import os
import re

import requests


class PlannerError(Exception):
    pass


def ask_json(system: str, prompt: str) -> dict:
    key = os.getenv("PLANNER_API_KEY")
    base = (os.getenv("PLANNER_BASE_URL") or "").rstrip("/")
    model = os.getenv("PLANNER_MODEL")
    if not (key and base and model):
        raise PlannerError("The trip planner is not configured.")
    try:
        r = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
            timeout=180,
        )
    except requests.RequestException:
        raise PlannerError("The trip planner could not respond. Please try again.")

    if r.status_code == 429:
        raise PlannerError("Too many requests right now. Please wait a moment and try again.")
    if r.status_code == 402:
        raise PlannerError("Planner credits have run out. Please add credits to continue.")
    if not r.ok:
        raise PlannerError("The trip planner could not respond. Please try again.")

    try:
        text = r.json()["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, ValueError):
        text = ""
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise PlannerError("The planner returned an unexpected answer. Please try again.")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        raise PlannerError("The planner returned an unexpected answer. Please try again.")
