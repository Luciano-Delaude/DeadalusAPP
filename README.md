## Rubric Validator CLI

Small helper CLI to send PR context and rubric drafts to an LLM for quick quality checks (atomic/specific/accurate/categorized/self-contained/grounded).

### Setup
- Requires Python 3.10+ and the `openai` package (`pip install openai`).
- Copy `.env.example` to `.env` and set `OPENAI_API_KEY` (and `OPENAI_BASE_URL` if you use a proxy/Azure/OpenRouter).

### Usage
```bash
# Dry-run: preview the prompt without calling the LLM
python rubric_validator.py \
  --pr-diff sample_data/pr_diff.txt \
  --repo-description sample_data/repo_description.txt \
  --rubrics sample_data/rubrics.json \
  --env-file .env \
  --dry-run

# Actual call (requires network + OPENAI_API_KEY)
python rubric_validator.py \
  --pr-diff sample_data/pr_diff.txt \
  --repo-description sample_data/repo_description.txt \
  --rubrics sample_data/rubrics.json \
  --env-file .env \
  --api-key $OPENAI_API_KEY \
  --base-url https://api.openai.com/v1 \
  --model gpt-4o-mini
```

### Web UI
- Install deps: `pip install -r requirements.txt`
- Start Streamlit UI: `streamlit run streamlit_app.py`
- Open the printed local URL to use the form (prefills available via buttons). The UI uses `OPENAI_API_KEY`/`OPENAI_BASE_URL` from `.env` and calls the default model `gpt-4o-mini`.

### Inputs
- `--pr-diff`: Path to a diff/patch file or plain text describing the PR.
- `--repo-description`: Short repository context file.
- `--rubrics`: JSON file containing a list of rubric objects:
  ```json
  [
    {
      "id": "R1",
      "type": "correctness",
      "importance": "high",
      "text": "Function calculate_discount in src/pricing.py returns 0 for negative totals."
    }
  ]
  ```
- Optional: `--show-prompt` to print the composed prompt alongside the request; `--dry-run` to only print the prompt.
- Optional: `--env-file`: Path to a `.env` containing `OPENAI_API_KEY` (default: `.env`).
- Optional: `--api-key`: Override `OPENAI_API_KEY` from the environment.
- Optional: `--base-url`: Override `OPENAI_BASE_URL` for custom gateways (OpenRouter/Azure/etc.).

Prompt now enforces grounding: rubrics citing files/functions not in the PR diff/repo description will be marked inaccurate/not grounded.
### Output
The LLM is asked to return JSON summarizing issues per rubric:
- Verdict plus flags for atomic/specific/accurate/categorized/self-contained/grounded.
- Notes and fixes so authors can quickly revise rubrics.

### Notes
- The script avoids failing when `openai` is missing by supporting `--dry-run`.
- You can swap `--model` to any chat-capable model your endpoint supports.
