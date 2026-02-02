import argparse
import json
import os
import sys
from textwrap import dedent
from typing import Any, Dict, List


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def load_rubrics(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Rubrics file must contain a JSON array of rubric objects.")
    for idx, rubric in enumerate(data):
        if not isinstance(rubric, dict) or "text" not in rubric:
            raise ValueError(f"Rubric at index {idx} must be an object with at least a 'text' field.")
    return data


def format_user_message(repo_description: str, pr_diff: str, rubrics: List[Dict[str, Any]]) -> str:
    rubric_lines = []
    for rubric in rubrics:
        rubric_id = rubric.get("id", "unlabeled")
        rubric_type = rubric.get("type", "unspecified")
        importance = rubric.get("importance", "unspecified")
        text = rubric.get("text", "").strip()
        rubric_lines.append(f"- [{rubric_id}] ({rubric_type}, {importance}) {text}")

    return dedent(
        f"""
        Repository description:
        {repo_description}

        Pull request diff or summary:
        {pr_diff}

        Rubrics to validate:
        {os.linesep.join(rubric_lines)}
        """
    ).strip()


SYSTEM_PROMPT = dedent(
    """
    You are a senior reviewer who scores rubric quality for evaluating PR review responses.

    For each rubric, check:
    - atomic: one clear aspect of the task.
    - specific: enough context/examples to remove ambiguity; if a function is mentioned, include its file path.
    - accurate: factually correct/logically sound relative to the PR context.
    - categorized: correct rubric type and importance level.
    - grounded: explicitly tied to the PR diff or repo description.
    - self-contained: can be assessed using only the rubric text and model response (no hidden context needed).

    Grounding discipline:
    - Only accept file paths or functions that actually appear in the PR diff or repo description. If a rubric cites a file/function not present, mark it inaccurate and not grounded.
    - If a rubric references work that is not in the PR diff (e.g., db.py when no such file is in the diff), treat it as inaccurate and not grounded, even if it seems plausible.
    - Prefer concrete anchors (paths, functions, line mentions) found in the provided diff/context.
    - If unsure whether a cited file/function exists in the provided context, assume it does NOT and mark inaccurate/not grounded.

    Also remember common rubric buckets:
    - correctness: evaluates final output functions.
    - style: assesses final output style.
    - agent-behavior: checks reasoning to find the right file/area.
    - summary: checks that the final text response summarizes code changes.

    Atomicity guidance:
    - Fail atomic if a rubric combines multiple distinct checks (e.g., "adds a Java or Kotlin test" + "reproduces IllegalStateException" + "asserts sessionAttribute doesn't create a new session").
    - "A or B" is non-atomic when A and B are different checks, languages, files, or behaviors. Treat that as multiple acceptable paths, not one aspect.
    - Pass atomic only when the rubric is a single check with a single observable outcome; optional details should be truly equivalent ways to verify the same behavior.
    - If in doubt, mark atomic = false and suggest splitting into separate rubrics.

    Return JSON with a list named "rubric_feedback". Each item:
    {{
      "id": "<rubric id>",
      "verdict": "pass" | "fail",
      "flags": {{
        "atomic": true/false,
        "specific": true/false,
        "accurate": true/false,
        "categorized": true/false,
        "grounded": true/false,
        "self_contained": true/false
      }},
      "issues": ["bullet pointing the main problems"],
      "suggested_fix": "rewrite that makes it compliant (keep empty if pass)"
    }}
    """
).strip()


def build_messages(repo_description: str, pr_diff: str, rubrics: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    user_message = format_user_message(repo_description, pr_diff, rubrics)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]


def call_llm(
    messages: List[Dict[str, str]], model: str, show_prompt: bool, api_key: str | None, base_url: str | None
) -> str:
    if show_prompt:
        print("=== SYSTEM PROMPT ===")
        print(messages[0]["content"])
        print("\n=== USER MESSAGE ===")
        print(messages[1]["content"])
        print("\n(LLM call follows)\n")

    effective_key = api_key or os.getenv("OPENAI_API_KEY")
    if not effective_key:
        raise RuntimeError("OPENAI_API_KEY is not set; export it or pass --api-key to send the request.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The 'openai' package is missing. Install it with `pip install openai`.") from exc

    client = OpenAI(api_key=effective_key, base_url=base_url or os.getenv("OPENAI_BASE_URL"))
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0,
    )
    content = response.choices[0].message.content or ""
    print(content)
    return content


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate rubric quality against a PR using an LLM.")
    parser.add_argument("--pr-diff", required=True, help="Path to a file containing the PR diff or summary.")
    parser.add_argument("--repo-description", required=True, help="Path to a short repo description file.")
    parser.add_argument("--rubrics", required=True, help="Path to a JSON file containing rubric objects.")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to a .env file with OPENAI_API_KEY/OPENAI_BASE_URL (default: .env).",
    )
    parser.add_argument("--api-key", help="Override OPENAI_API_KEY from env.")
    parser.add_argument("--base-url", help="Override OPENAI_BASE_URL from env (e.g., https://api.openai.com/v1).")
    parser.add_argument("--model", default="gpt-4o-mini", help="Chat model to use (default: gpt-4o-mini).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the constructed prompt and exit without calling the LLM.",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Echo the prompt before sending it to the LLM.",
    )
    args = parser.parse_args()

    try:
        repo_description = read_text(args.repo_description)
        pr_diff = read_text(args.pr_diff)
        rubrics = load_rubrics(args.rubrics)
        messages = build_messages(repo_description, pr_diff, rubrics)

        if args.dry_run:
            print("=== SYSTEM PROMPT ===")
            print(messages[0]["content"])
            print("\n=== USER MESSAGE ===")
            print(messages[1]["content"])
            print("\n(dry-run mode: no LLM call made)")
            return

        call_llm(messages, args.model, args.show_prompt, args.api_key, args.base_url)
    except Exception as exc:  # pragma: no cover - minimal utility script
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
