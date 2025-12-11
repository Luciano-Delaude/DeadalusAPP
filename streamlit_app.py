import json
import os

import streamlit as st
from streamlit.runtime.secrets import StreamlitSecretNotFoundError

from rubric_validator import build_messages, call_llm

st.set_page_config(page_title="Rubric Validator", layout="wide")

# Load secrets (Streamlit Cloud) and local .env fallback.
secrets_dict: dict[str, str] = {}
try:
    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "ENABLE_DRY_RUN"):
        if key in st.secrets:
            val = st.secrets[key]
            if val is not None:
                secrets_dict[key] = str(val)
except StreamlitSecretNotFoundError:
    secrets_dict = {}
if secrets_dict:
    os.environ.update(secrets_dict)

MODEL_DEFAULT = "openai/gpt-4o-mini"
MODEL_CHOICES = [
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "openai/gpt-4.1",
    "openai/gpt-5.1",
    "openai/gpt-4.1-mini",
    "deepseek/deepseek-chat",
    "deepseek/deepseek-r1",
    "anthropic/claude-3.5-sonnet"
]
st.title("Rubric Validator")
st.write("Validate rubric quality against a PR context.")


def describe_key(key: str | None) -> str:
    if not key:
        return "<missing>"
    return f"present (len={len(key)}, endswith=...{key[-4:]})"


# Session state defaults
default_rubrics = [
    {
        "id": "R1",
        "type": "correctness",
        "importance": "must-follow",
        "positive": True,
        "text": "Function calculate_discount in src/pricing.py must return 0 for negative totals.",
    },
    {
        "id": "R2",
        "type": "code style",
        "importance": "good-to-have",
        "positive": True,
        "text": "Email subjects and bodies should look consistent.",
    },
]
if "repo_description" not in st.session_state:
    st.session_state["repo_description"] = ""
if "pr_diff" not in st.session_state:
    st.session_state["pr_diff"] = ""
if "rubrics" not in st.session_state:
    st.session_state["rubrics"] = default_rubrics
if "model" not in st.session_state:
    st.session_state["model"] = MODEL_DEFAULT

# Inputs
st.markdown("### Model")
st.session_state["model"] = st.selectbox("Choose model", MODEL_CHOICES, index=MODEL_CHOICES.index(MODEL_DEFAULT))
repo_description = st.text_area("Repository Description", height=120, key="repo_description")
pr_diff = st.text_area("PR Diff / Summary", height=200, key="pr_diff")

with st.expander("Debug: secrets and environment (keys are masked)"):
    # Show Streamlit secrets (masked) and whether they exist in os.environ
    def mask_val(v: str | None) -> str:
        if not v:
            return "<missing>"
        return f"present (len={len(v)}, endswith=...{v[-4:]})"

    try:
        secrets_preview = {k: mask_val(st.secrets.get(k)) for k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "ENABLE_DRY_RUN")}
    except Exception:
        secrets_preview = {"OPENAI_API_KEY": "<no secrets available>", "OPENAI_BASE_URL": "<no secrets available>", "ENABLE_DRY_RUN": "<no secrets available>"}

    st.write("Streamlit secrets (masked):")
    st.json(secrets_preview)

    env_preview = {"OPENAI_API_KEY": mask_val(os.getenv("OPENAI_API_KEY")), "OPENAI_BASE_URL": os.getenv("OPENAI_BASE_URL", "<missing>"), "ENABLE_DRY_RUN": os.getenv("ENABLE_DRY_RUN", "<missing>")}
    st.write("os.environ (masked):")
    st.json(env_preview)

    if st.button("Sync secrets to env"):
        try:
            # Copy known keys from st.secrets into os.environ
            for k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "ENABLE_DRY_RUN"):
                if k in st.secrets and st.secrets[k] is not None:
                    os.environ[k] = str(st.secrets[k])
            st.success("Secrets copied to environment. Rerun the action (Validate) now.")
            st.experimental_rerun()
        except Exception as exc:
            st.error(f"Failed to sync secrets: {exc}")

st.markdown("### Rubrics")
st.write("Add as many as you need. Each rubric has an ID, type, importance, positive flag, and text.")

# Render dynamic rubric inputs
for idx, rubric in enumerate(list(st.session_state["rubrics"])):
    with st.expander(f"Rubric {idx + 1}: {rubric.get('id', f'R{idx+1}')}", expanded=True):
        new_id = st.text_input("ID", value=rubric.get("id", f"R{idx+1}"), key=f"id_{idx}")
        type_options = ["correctness", "code style", "summary", "agent behavior", "other"]
        current_type = rubric.get("type", "correctness")
        type_index = type_options.index(current_type) if current_type in type_options else 0
        new_type = st.selectbox("Type", type_options, index=type_index, key=f"type_{idx}")

        importance_options = ["must-follow", "good-to-have", "universal"]
        current_importance = rubric.get("importance", "must-follow")
        importance_index = importance_options.index(current_importance) if current_importance in importance_options else 0
        new_importance = st.radio(
            "Importance",
            options=importance_options,
            index=importance_index,
            key=f"importance_{idx}",
            format_func=lambda x: {"must-follow": "Must Follow", "good-to-have": "Good to have", "universal": "Universal"}.get(x, x),
        )

        current_positive = bool(rubric.get("positive", True))
        new_positive = st.radio(
            "Is the criterion positive?",
            options=[True, False],
            index=0 if current_positive else 1,
            key=f"positive_{idx}",
            format_func=lambda x: "True" if x else "False",
        )

        new_text = st.text_area("Text", value=rubric.get("text", ""), height=120, key=f"text_{idx}")
        st.session_state["rubrics"][idx] = {
            "id": new_id,
            "type": new_type,
            "importance": new_importance,
            "positive": new_positive,
            "text": new_text,
        }
        if st.button("Remove this rubric", key=f"remove_{idx}"):
            st.session_state["rubrics"].pop(idx)
            st.rerun()

if st.button("Add rubric"):
    new_idx = len(st.session_state["rubrics"]) + 1
    st.session_state["rubrics"].append(
        {"id": f"R{new_idx}", "type": "correctness", "importance": "must-follow", "positive": True, "text": ""}
    )
    st.rerun()

# Bulk load rubrics from pasted JSON (id/title/annotations format)
st.markdown("### Load rubrics from JSON")
json_input = st.text_area(
    "Paste rubric JSON (array with title and annotations fields)",
    height=200,
    value="",
    placeholder='[{"id":"...","title":"...","annotations":{"is_positive":"true","importance":"must follow","type":"correctness","rationale":"..."}}]',
)
if st.button("Replace rubrics with pasted JSON"):
    try:
        raw_items = json.loads(json_input)
        if not isinstance(raw_items, list):
            raise ValueError("JSON must be an array.")

        mapped = []
        importance_map = {
            "must follow": "must-follow",
            "good to have": "good-to-have",
            "universal": "universal",
        }
        for idx, item in enumerate(raw_items):
            if not isinstance(item, dict):
                continue
            annotations = item.get("annotations", {}) if isinstance(item.get("annotations", {}), dict) else {}
            title = (item.get("title") or "").strip()
            importance_raw = (annotations.get("importance") or "").strip().lower()
            importance = importance_map.get(importance_raw, importance_raw or "must-follow")
            type_raw = (annotations.get("type") or "").strip().lower()
            rubric_type = type_raw if type_raw in ["correctness", "code style", "summary", "agent behavior", "other"] else "correctness"
            is_positive_raw = annotations.get("is_positive")
            if isinstance(is_positive_raw, str):
                positive = is_positive_raw.strip().lower() == "true"
            else:
                positive = bool(is_positive_raw) if is_positive_raw is not None else True

            mapped.append(
                {
                    "id": item.get("id", f"R{idx+1}"),
                    "type": rubric_type,
                    "importance": importance,
                    "positive": positive,
                    "text": title,
                }
            )

        if not mapped:
            raise ValueError("No valid rubric objects found.")

        st.session_state["rubrics"] = mapped
        st.success(f"Loaded {len(mapped)} rubrics from JSON.")
        st.rerun()
    except Exception as exc:
        st.error(f"Failed to parse JSON: {exc}")

run = st.button("Validate")

# Optional: enable dry-run only if admin flag is set in secrets (ENABLE_DRY_RUN=true)
enable_dry_run = False
try:
    enable_dry_run = bool(st.secrets.get("ENABLE_DRY_RUN", False))
except Exception:
    enable_dry_run = False
dry_run = False
if enable_dry_run:
    dry_run = st.button("Dry Run (prompt only)")

status_placeholder = st.empty()
result_placeholder = st.empty()


def handle(dry: bool):
    rubrics = st.session_state.get("rubrics", [])
    rubric_lookup = {r.get("id"): r for r in rubrics if isinstance(r, dict) and r.get("id")}
    messages = build_messages(
        st.session_state.get("repo_description", ""),
        st.session_state.get("pr_diff", ""),
        rubrics,
    )

    if dry:
        status_placeholder.info("Dry-run: showing prompt.")
        result_placeholder.code(json.dumps({"messages": messages}, indent=2), language="json")
        return

    status_placeholder.info("Calling LLM...")
    try:
        content = call_llm(
            messages,
            st.session_state.get("model", MODEL_DEFAULT),
            False,
            os.getenv("OPENAI_API_KEY"),
            os.getenv("OPENAI_BASE_URL"),
        )
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {"raw": content}

        # Render structured output if rubric_feedback exists
        feedback = parsed.get("rubric_feedback") if isinstance(parsed, dict) else None
        if feedback and isinstance(feedback, list):
            for idx, item in enumerate(feedback):
                rubric_id = item.get("id", "") if isinstance(item, dict) else ""
                original = rubric_lookup.get(rubric_id) or (rubrics[idx] if idx < len(rubrics) else {})
                item_type = item.get("type") if isinstance(item, dict) else None
                item_importance = item.get("importance") if isinstance(item, dict) else None
                item_positive = item.get("positive") if isinstance(item, dict) else None
                item_text = item.get("text") if isinstance(item, dict) else None

                st.subheader(f"Rubric {idx + 1}: {rubric_id}")
                st.write(f"Type: {item_type or original.get('type', 'n/a')}")
                st.write(f"Importance: {item_importance or original.get('importance', 'n/a')}")
                st.write(f"Positive: {item_positive if item_positive is not None else original.get('positive', 'n/a')}")
                st.write(f"Text: {item_text or original.get('text', 'n/a')}")
                if isinstance(item, dict):
                    verdict = item.get("verdict", "")
                    verdict_color = "green" if str(verdict).lower() == "pass" else "red"
                    st.markdown(f"**Verdict:** <span style='color:{verdict_color}'>{verdict}</span>", unsafe_allow_html=True)
                    issues = item.get("issues", [])
                    suggested = item.get("suggested_fix", "")
                    if issues:
                        st.markdown("**Issues:**")
                        for issue in issues:
                            st.write(f"- {issue}")
                    if suggested:
                        st.markdown("**Suggested fix:**")
                        st.write(suggested)
        else:
            result_placeholder.json(parsed)

        status_placeholder.success("Done")
    except Exception as exc:  # pragma: no cover - UI only
        status_placeholder.error(f"Error: {exc}")


if run:
    handle(False)
elif dry_run:
    handle(True)
