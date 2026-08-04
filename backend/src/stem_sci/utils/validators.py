"""Small validation helpers shared by framework adapters."""


def require_nonempty(value: str, field: str) -> str:
    if not value.strip():
        raise ValueError(f"{field} must not be empty")
    return value


def require_reference(value: str, prefix: str) -> str:
    require_nonempty(value, "reference")
    expected = f"{prefix}://"
    if not value.startswith(expected):
        raise ValueError(f"reference must start with {expected}")
    return value
