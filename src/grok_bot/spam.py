import re
from dataclasses import dataclass
from typing import Optional


TRIVIAL_STRINGS = {"hi", "hello", "test", "ping"}


@dataclass
class ValidationResult:
    ok: bool
    reason: Optional[str] = None
    reply: Optional[str] = None


def _looks_gibberish(text: str) -> bool:
    text = text.lower()
    letters = re.sub(r"[^a-z]", "", text)
    if not letters:
        return False
    unique_chars = set(letters)
    if len(unique_chars) <= 2 and len(letters) >= 6:
        return True
    repeating = re.match(r"^([a-z]{1,3})\1{2,}$", letters)
    return bool(repeating)


def validate_prompt(prompt: str, *, max_chars: int) -> ValidationResult:
    cleaned = prompt.strip()
    if not cleaned:
        return ValidationResult(
            ok=False,
            reason="empty",
            reply="Try sending an actual question instead of blank air.",
        )
    if len(cleaned) < 5:
        return ValidationResult(
            ok=False,
            reason="too_short",
            reply="That barely qualifies as a question. Add some words.",
        )
    lowered = cleaned.lower()
    if lowered in TRIVIAL_STRINGS:
        return ValidationResult(
            ok=False, reason="trivial", reply="Wow, groundbreaking. Try a real question."
        )
    if _looks_gibberish(cleaned):
        return ValidationResult(
            ok=False, reason="gibberish", reply="That looks like keyboard smash. Try again."
        )
    if len(cleaned) > max_chars:
        return ValidationResult(
            ok=False,
            reason="too_long",
            reply=f"Message is too long. Trim it under {max_chars} characters.",
        )
    return ValidationResult(ok=True, reason=None, reply=None)
