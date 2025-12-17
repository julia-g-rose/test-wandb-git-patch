"""Add file description here"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import dotenv
import wandb
import yaml

import weave
from openai import OpenAI

from tools.tool_call import get_weather


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@weave.op()
def call_openai_once(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int | None = None,
    top_p: float | None = None,
    tool_choice: str = "auto",
) -> str:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    tools = None
    tool_choice_norm = (tool_choice or "auto").strip().lower()
    enable_tools = tool_choice_norm != "none"
    if enable_tools:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get a brief weather summary for a location (demo stub; no external API).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "City/region name, e.g. 'Tokyo' or 'London'",
                            },
                            "date": {
                                "type": "string",
                                "description": "Optional date like '2025-12-17'",
                            },
                            "units": {
                                "type": "string",
                                "description": "Temperature unit: 'C' or 'F'",
                            }
                        },
                        "required": ["location"],
                        "additionalProperties": False,
                    },
                },
            }
        ]

    # 1st call: model may decide to call the tool.
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        messages=messages,
        tools=tools,
        tool_choice=(tool_choice_norm if enable_tools else None),
    )

    msg = resp.choices[0].message
    tool_calls = getattr(msg, "tool_calls", None) or []
    if not tool_calls:
        return msg.content or ""

    # Execute tool calls and send results back.
    messages.append(msg.model_dump())
    for tc in tool_calls:
        if tc.function.name != "get_weather":
            continue
        args = tc.function.arguments
        # OpenAI SDK gives JSON string for arguments.
        import json

        parsed = json.loads(args) if isinstance(args, str) else (args or {})
        tool_out = get_weather(
            location=str(parsed.get("location", "")),
            date=(str(parsed["date"]) if "date" in parsed and parsed["date"] is not None else None),
            units=str(parsed.get("units", "C")),
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(tool_out),
            }
        )

    resp2 = client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        messages=messages,
    )
    return resp2.choices[0].message.content or ""


def main() -> int:
    parser = argparse.ArgumentParser(description="W&B code/patch + Weave trace smoke test")
    parser.add_argument(
        "--run-name",
        dest="run_name",
        default=None,
        help="Optional W&B run display name (overrides WANDB_RUN_NAME if set).",
    )
    args = parser.parse_args()

    dotenv.load_dotenv()

    entity = os.getenv("WANDB_ENTITY")
    project = os.getenv("WANDB_PROJECT")
    if not entity or not project:
        raise RuntimeError("Set WANDB_ENTITY and WANDB_PROJECT in .env")
    if not os.getenv("WANDB_API_KEY"):
        raise RuntimeError("Set WANDB_API_KEY in .env")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY in .env")

    run_name = args.run_name or os.getenv("WANDB_RUN_NAME")

    repo_root = Path(__file__).resolve().parent
    system_prompt_path = repo_root / "prompts" / "system_prompt.txt"
    hparams_path = repo_root / "config" / "hparams.yaml"

    system_prompt = _read_text(system_prompt_path)
    hparams = _read_yaml(hparams_path)

    model = str(hparams.get("model", "gpt-4o-mini"))
    temperature = float(hparams.get("temperature", 0.2))
    max_tokens = hparams.get("max_tokens", 128)
    top_p = hparams.get("top_p", 1.0)
    tool_choice = str(hparams.get("tool_choice", "auto"))

    # Weave traces will appear under this project.
    weave_project = os.getenv("WEAVE_PROJECT") or project
    weave.init(weave_project)

    run = wandb.init(
        entity=entity,
        project=project,
        name=run_name,
        job_type="git-patch-weave-smoketest",
        config={
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "tool_choice": tool_choice,
            "system_prompt_path": str(system_prompt_path),
            "hparams_path": str(hparams_path),
        },
        save_code=True,
    )

    # Log *all* files under repo_root (W&B defaults to only *.py unless include_fn is overridden).
    def _include_all(_path: str, _root: str) -> bool:
        return True

    def _exclude_noise(path: str, root: str) -> bool:
        rel = os.path.relpath(path, root)
        # Exclude common large/secret/derived dirs and files.
        if rel == ".env" or rel.startswith(".env" + os.sep):
            return True
        for prefix in (
            ".git" + os.sep,
            "venv" + os.sep,
            ".venv" + os.sep,
            "wandb" + os.sep,
            ".wandb" + os.sep,
            "__pycache__" + os.sep,
        ):
            if rel.startswith(prefix):
                return True
        # Skip pyc files anywhere.
        if rel.endswith(".pyc"):
            return True
        return False

    run.log_code(root=str(repo_root), include_fn=_include_all, exclude_fn=_exclude_noise)

    user_prompt = (
        "You are helping plan a 2-day trip.\n"
        "Destination: Tokyo.\n"
        "Dates: 2025-12-17 to 2025-12-18.\n"
        "Budget: mid-range.\n\n"
        "Call get_weather for Tokyo for 2025-12-17, then propose a 2-day itinerary that adapts to the weather. "
        "Include 3 activities per day and a short packing list."
    )

    tool_result: dict[str, Any] | None = None
    if str(tool_choice).strip().lower() != "none":
        # Log an example tool input (not secrets) so you can see it in W&B.
        tool_result = {"tool": "get_weather", "location": "Tokyo", "date": "2025-12-17", "units": "C"}
        wandb.log({"tool_hint": tool_result})

    answer = call_openai_once(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        tool_choice=tool_choice,
    )

    wandb.log(
        {
            "prompt/user_prompt": user_prompt,
            "prompt/system_prompt": system_prompt,
            "openai/answer": answer,
        }
    )

    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


