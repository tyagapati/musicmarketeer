"""Persisted admin toggles for background automation."""
from app import db
from app.models import AppSetting

AUTOMATION_TOGGLES = {
    "auto_approve_marketers": {
        "label": "Auto-approve marketers",
        "help": (
            "When on, discovery and cleanup can automatically approve marketers that pass "
            "confidence thresholds (≥75 confidence, ≥50 proof, services + genres present). "
            "When off, all new discoveries stay pending until you approve manually."
        ),
        "default": False,
    },
}


def ensure_automation_defaults():
    """Seed default toggle values (all off) for keys not yet stored."""
    changed = False
    for key, meta in AUTOMATION_TOGGLES.items():
        if AppSetting.query.get(key) is None:
            db.session.add(AppSetting(key=key, value="true" if meta["default"] else "false"))
            changed = True
    if changed:
        db.session.commit()


def is_automation_enabled(key):
    ensure_automation_defaults()
    row = AppSetting.query.get(key)
    if row is None:
        return bool(AUTOMATION_TOGGLES.get(key, {}).get("default", False))
    return row.value.strip().lower() in ("1", "true", "yes", "on")


def set_automation_enabled(key, enabled):
    if key not in AUTOMATION_TOGGLES:
        raise KeyError(key)
    row = AppSetting.query.get(key)
    value = "true" if enabled else "false"
    if row is None:
        db.session.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


def automation_toggle_states():
    ensure_automation_defaults()
    states = []
    for key, meta in AUTOMATION_TOGGLES.items():
        states.append(
            {
                "key": key,
                "label": meta["label"],
                "help": meta["help"],
                "enabled": is_automation_enabled(key),
            }
        )
    return states
