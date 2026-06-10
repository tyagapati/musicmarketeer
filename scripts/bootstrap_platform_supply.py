"""Promote approved marketers to platform supply with starter packages."""
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv(override=True)

from app import create_app, db
from app.models import Marketer, MarketerPackage


def main():
    app = create_app()
    with app.app_context():
        candidates = Marketer.query.filter_by(status="approved").all()
        enrolled = 0
        packages_added = 0
        for m in candidates:
            if not m.enrolled:
                m.provider_type = "solo"
                m.enrolled = True
                enrolled += 1
            if not m.portal_token:
                m.portal_token = secrets.token_urlsafe(24)
            if not MarketerPackage.query.filter_by(marketer_id=m.id, active=True).first():
                service = (m.services or ["playlist_pitching"])[0]
                price = max(49, m.price_min or 149)
                db.session.add(
                    MarketerPackage(
                        marketer_id=m.id,
                        service=service,
                        title=f"{m.brand_name or m.name} — starter package",
                        description=m.bio or "Platform marketplace package.",
                        price_cents=price * 100,
                        delivery_days=14,
                        active=True,
                    )
                )
                packages_added += 1
        db.session.commit()
        platform_count = Marketer.query.filter_by(status="approved", enrolled=True, provider_type="solo").count()
        pkg_count = MarketerPackage.query.filter_by(active=True).count()
        print(f"Enrolled {enrolled} marketers, added {packages_added} packages.")
        print(f"Platform marketers: {platform_count}, active packages: {pkg_count}")


if __name__ == "__main__":
    main()
