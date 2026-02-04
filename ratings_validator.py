import json
from typing import Dict, List


def build_ratings_messages(summary: str, pr_diff: str, ratings: Dict, rubric_lookup: Dict[str, Dict]) -> List[Dict[str, str]]:
    system_prompt = """
You are an expert auditor of rubric ratings and justifications for PR review responses.
Inputs you receive:
- PR diff/summary
- A model response summary (what the model did)
- Rubric ratings JSON: maps response ids -> rubric ids with title/score/color/justification

For each rating, verify:
- Grounding: the justification cites facts present in the PR diff/summary or response summary. If it references files/behavior not in context, it is not grounded.
- Consistency: score/title/color align with the justification (e.g., if justification describes a failure, score/title should be fail/red; if it describes success, score/title should be pass/green).
- Clarity: justification clearly explains why the rating is correct given the rubric.

Always return feedback for every rating, even if it is OK. The verdict must be "ok" or "incorrect".
When verdict is "ok", explain briefly why the rating is acceptable, with specific grounding anchors (file paths, functions, or diff facts) and why the justification matches the score/title/color.
When verdict is "incorrect", explain why (grounding/consistency/clarity) and suggest a corrected rating and/or rewritten justification.

Focus on grounding and consistency first; clarity is secondary. If any grounding or consistency issue exists, verdict must be "incorrect".

Return JSON:
{
  "rating_feedback": [
    {
      "response_id": "...",
      "rubric_id": "...",
      "verdict": "ok" | "incorrect",
      "issues": ["bullet list of problems or confirmations"],
      "suggested_fix": "rewrite or corrected rating; keep empty string if ok"
    }
  ]
}
"""
    user_content = f"PR diff/summary:\n{pr_diff}\n\nResponse summary:\n{summary}\n\nRubric ratings JSON:\n{json.dumps(ratings, indent=2)}\n\nRubric definitions (by id):\n{json.dumps(rubric_lookup, indent=2)}"
    return [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_content},
    ]
