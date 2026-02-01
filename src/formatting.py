import json
import re

_LEADING_NUM_RE = re.compile(r"^\s*(?:step\s*)?\(?\d+\)?\s*[\.\):\-]\s*", re.IGNORECASE)


def _print_devin_output(data: dict):
    """Format and print Devin output in a human-friendly way."""
    so = data.get("structured_output")
    try:
        formatted = _format_structured_output(so)
        if formatted:
            print(formatted)
            return
    except Exception:
        # Fall through to other fallbacks
        pass

    messages = data.get("messages") or []
    if messages:
        last = messages[-1]
        if isinstance(last, dict):
            last_text = last.get("content") or last.get("message") or json.dumps(last, indent=2)
        else:
            last_text = str(last)
        print("\nLatest Devin message:\n")
        print(last_text)
        return

    print("\nNo output returned.")


def _format_structured_output(so: dict | None) -> str | None:
    """Return a nicely formatted string for structured_output; None if not printable."""
    if not isinstance(so, dict):
        return None

    lines = []
    mode = so.get("mode")
    clarify = so.get("clarify") or {}
    plan = so.get("plan") or {}

    def fmt_list(name, items, strip_nums: bool = False):
        if not isinstance(items, list) or not items:
            return
        lines.append(f"{name}:")
        for i, item in enumerate(items, 1):
            text = str(item)
            if strip_nums:
                text = _LEADING_NUM_RE.sub("", text).strip()
            lines.append(f"  {i}. {text}")

    if mode == "clarify":
        qs = clarify.get("questions")
        whys = clarify.get("why_needed")
        conf = clarify.get("confidence")
        lines.append("== Clarifying Questions ==")
        if isinstance(qs, list) and isinstance(whys, list) and len(qs) == len(whys):
            for i, (q, w) in enumerate(zip(qs, whys), 1):
                lines.append(f"{i}. {q}")
                lines.append(f"   why: {w}")
        elif isinstance(qs, list):
            fmt_list("Questions", qs)
        if isinstance(conf, (int, float)):
            lines.append(f"Confidence: {conf:.2f}")
    else:
        # default to plan view
        lines.append("== Plan ==")
        summary = plan.get("summary")
        if summary:
            lines.append(f"Summary: {summary}")
        steps = plan.get("plan_steps")
        fmt_list("Steps", steps, strip_nums=True)
        risks = plan.get("risks")
        fmt_list("Risks", risks)
        conf = plan.get("confidence")
        if isinstance(conf, (int, float)):
            lines.append(f"Confidence: {conf:.2f}")

    if not lines:
        return None
    return "\n".join([""] + lines)  # leading blank line for spacing
