"""Boost marketer proof scores from hire feedback outcomes."""
from sqlalchemy import func

from app import db
from app.models import Marketer, MatchFeedback


def refresh_outcome_scores():
    """Increase proof_strength for marketers with confirmed hires."""
    hire_counts = (
        db.session.query(MatchFeedback.marketer_id, func.count(MatchFeedback.id))
        .filter(MatchFeedback.hired.is_(True))
        .group_by(MatchFeedback.marketer_id)
        .all()
    )
    updated = 0
    for marketer_id, hire_count in hire_counts:
        marketer = Marketer.query.get(marketer_id)
        if not marketer:
            continue
        boost = min(25, hire_count * 5)
        new_score = min(100, (marketer.proof_strength or 0) + boost)
        if new_score != marketer.proof_strength:
            marketer.proof_strength = new_score
            updated += 1
    db.session.commit()
    return {"updated": updated, "marketers_with_hires": len(hire_counts)}
