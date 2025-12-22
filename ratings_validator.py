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
- Grounding: justification cites facts present in the PR diff/summary. If it references files/behavior not in context, it is not grounded/accurate.
- Consistency: score/title/color align with the justification (e.g., if justification describes a failure, score/title should be fail/red; if it describes success, score/title should be pass/green).
- Clarity: justification clearly explains why the rating is correct.

If a rating is wrong or unsupported, mark it incorrect and suggest a corrected rating/justification.

Return JSON:
{
  "rating_feedback": [
    {
      "response_id": "...",
      "rubric_id": "...",
      "verdict": "ok" | "incorrect",
      "issues": ["bullet list of problems"],
      "suggested_fix": "rewrite or corrected rating"
    }
  ]
}
"""
    user_content = f"PR diff/summary:\n{pr_diff}\n\nResponse summary:\n{summary}\n\nRubric ratings JSON:\n{json.dumps(ratings, indent=2)}\n\nRubric definitions (by id):\n{json.dumps(rubric_lookup, indent=2)}"
    return [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_content},
    ]
