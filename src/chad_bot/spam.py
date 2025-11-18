import re
from dataclasses import dataclass
from typing import Optional

from .yaml_config import YAMLConfig


# Pre-compiled regex patterns for improved performance
TRIVIAL_STRINGS = {"hi", "hello", "test", "ping"}
PATTERN_NON_ALPHA = re.compile(r"[^a-z]")
PATTERN_REPEATING = re.compile(r"^([a-z]{1,4})\1{2,}$")
KEYBOARD_ROWS = [
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
    "1234567890"
]
# Pre-compile keyboard row patterns for efficient matching
KEYBOARD_PATTERNS = [re.compile(re.escape(row[i:i+4])) for row in KEYBOARD_ROWS for i in range(len(row) - 3)]

@dataclass
class ValidationResult:
    ok: bool
    reason: Optional[str] = None
    reply: Optional[str] = None


def _looks_gibberish(text: str) -> bool:
    """
    Improved gibberish detection using multiple heuristics.
    Returns True if text appears to be nonsense/spam.
    """
    text_lower = text.lower()
    letters = PATTERN_NON_ALPHA.sub("", text_lower)
    
    if not letters or len(letters) < 4:
        return False
    
    unique_chars = set(letters)
    
    # Very low character variety (e.g., "aaaaaaa" or "ababab")
    if len(unique_chars) <= 2 and len(letters) >= 6:
        return True
    
    # Check for repeating patterns (e.g., "asdasdasd", "123123123")
    if PATTERN_REPEATING.match(letters):
        return True
    
    # Check for keyboard mashing patterns (consecutive keys)
    # Common patterns: qwerty, asdf, zxcv, consecutive numbers
    for row in KEYBOARD_ROWS:
        # Check for 4+ consecutive characters from same keyboard row
        for i in range(len(row) - 3):
            pattern = row[i:i+4]
            if pattern in text_lower or pattern[::-1] in text_lower:
                return True
    
    # Check consonant-to-vowel ratio (real words typically have vowels)
    vowels = set("aeiou")
    vowel_count = sum(1 for c in letters if c in vowels)
    consonant_count = len(letters) - vowel_count
    
    # If more than 80% consonants or no vowels at all (for longer text)
    if len(letters) >= 6:
        if vowel_count == 0:
            return True
        if consonant_count / len(letters) > 0.85:
            return True
    
    # Check for excessive character repetition (e.g., "heeeeelllllp")
    max_consecutive = 0
    current_char = None
    current_count = 0
    
    for char in letters:
        if char == current_char:
            current_count += 1
            max_consecutive = max(max_consecutive, current_count)
        else:
            current_char = char
            current_count = 1
    
    # If any character repeats more than 4 times consecutively
    if max_consecutive > 4:
        return True
    
    return False


def validate_prompt(prompt: str, *, max_chars: int, yaml_config: Optional[YAMLConfig] = None) -> ValidationResult:
    """
    Validate user prompt for spam, gibberish, and other issues.
    Uses YAML config for messages if provided, otherwise uses defaults.
    """
    if yaml_config is None:
        yaml_config = YAMLConfig()
    
    cleaned = prompt.strip()
    if not cleaned:
        return ValidationResult(
            ok=False,
            reason="empty",
            reply=yaml_config.get_message("empty_input"),
        )
    if len(cleaned) < 5:
        return ValidationResult(
            ok=False,
            reason="too_short",
            reply=yaml_config.get_message("too_short"),
        )
    lowered = cleaned.lower()
    if lowered in TRIVIAL_STRINGS:
        return ValidationResult(
            ok=False, 
            reason="trivial", 
            reply=yaml_config.get_message("trivial_input")
        )
    if _looks_gibberish(cleaned):
        return ValidationResult(
            ok=False, 
            reason="gibberish", 
            reply=yaml_config.get_message("gibberish")
        )
    if len(cleaned) > max_chars:
        return ValidationResult(
            ok=False,
            reason="too_long",
            reply=yaml_config.get_message("too_long", max_chars=max_chars),
        )
    return ValidationResult(ok=True, reason=None, reply=None)
