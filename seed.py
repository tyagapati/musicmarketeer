"""
Seed script to populate database with sample data.
"""
from app import create_app, db
from app.models import Marketer, CampaignBrief
from app.services.matching import rank_marketers
from datetime import datetime


def seed_marketers():
    """Seed 10 fake marketers."""
    marketers_data = [
        {
            'name': 'Jordan Lee',
            'brand_name': 'Playlist Pro',
            'website': 'https://playlistpro.example.com',
            'email': 'jordan@playlistpro.example.com',
            'bio': 'Specialized in playlist pitching for indie and pop artists. 5+ years experience with editorial and independent playlists.',
            'genres': ['indie', 'pop', 'indie-pop'],
            'services': ['playlist_pitching', 'release_campaigns'],
            'languages': ['en'],
            'timezone': 'America/New_York',
            'geography': 'US',
            'price_min': 150,
            'price_max': 600,
            'price_model': 'fixed',
 'preferred_maturity': ['early', 'mid'],
            'portfolio_urls': ['https://playlistpro.example.com/portfolio'],
            'evidence_summary': 'Strong track record with 200+ successful playlist adds',
            'proof_strength': 70,
            'source': 'manual',
            'status': 'approved',
            'confidence_score': 75,
        },
        {
            'name': 'Nia Carter',
            'brand_name': 'Carter Music Marketing',
            'website': 'https://cartermusic.example.com',
            'email': 'nia@cartermusic.example.com',
            'bio': 'Full-service music marketing agency specializing in hip-hop, R&B, and afrobeats. End-to-end campaigns from strategy to execution.',
            'genres': ['hip-hop', 'r&b', 'afrobeats'],
            'services': ['identity_positioning', 'social_media_strategy', 'ads', 'pr', 'release_campaigns', 'analytics'],
            'languages': ['en'],
            'timezone': 'America/New_York',
            'geography': 'US',
            'price_min': 2000,
            'price_max': 10000,
            'price_model': 'retainer',
            'preferred_maturity': ['mid', 'advanced'],
            'portfolio_urls': ['https://cartermusic.example.com/case-studies'],
            'evidence_summary': 'Agency with proven results for major label and independent artists',
            'proof_strength': 85,
            'source': 'manual',
            'status': 'approved',
            'confidence_score': 90,
        },
        {
            'name': 'Carlos Rivera',
            'brand_name': 'Rivera Ads',
            'website': 'https://riveraads.example.com',
            'email': 'carlos@riveraads.example.com',
            'bio': 'Paid advertising specialist for all genres. Expert in Meta, TikTok, and YouTube ads with bilingual support.',
            'genres': ['hip-hop', 'pop', 'latin-pop', 'reggaeton', 'electronic'],
            'services': ['ads', 'analytics'],
            'languages': ['en', 'es'],
            'timezone': 'America/Chicago',
            'geography': 'US',
            'price_min': 500,
            'price_max': 2500,
            'price_model': 'range',
            'preferred_maturity': ['early', 'mid', 'advanced'],
            'portfolio_urls': ['https://riveraads.example.com/results'],
            'evidence_summary': 'Consistent ROI improvements for clients across genres',
            'proof_strength': 75,
            'source': 'manual',
            'status': 'approved',
            'confidence_score': 80,
        },
        {
            'name': 'Priya Sharma',
            'brand_name': 'Sharma Social',
            'website': 'https://sharmasocial.example.com',
            'email': 'priya@sharmasocial.example.com',
            'bio': 'Social media strategist focusing on pop, electronic, and Bollywood. Content calendars, engagement strategies, and growth tactics.',
            'genres': ['pop', 'electronic', 'bollywood'],
            'services': ['social_media_strategy', 'short_form_content', 'community_growth'],
            'languages': ['en', 'hi'],
            'timezone': 'America/Los_Angeles',
            'geography': 'Global',
            'price_min': 300,
            'price_max': 1200,
            'price_model': 'retainer',
            'preferred_maturity': ['early', 'mid'],
            'portfolio_urls': ['https://sharmasocial.example.com/work'],
            'evidence_summary': 'Helped artists grow from 1K to 100K+ followers',
            'proof_strength': 60,
            'source': 'manual',
            'status': 'approved',
            'confidence_score': 65,
        },
        {
            'name': 'Marcus Johnson',
            'brand_name': 'Johnson PR',
            'website': 'https://johnsonpr.example.com',
            'email': 'marcus@johnsonpr.example.com',
            'bio': 'Music PR specialist with deep connections in hip-hop and R&B media. Blog placements, press releases, and influencer seeding.',
            'genres': ['hip-hop', 'r&b'],
            'services': ['pr', 'identity_positioning'],
            'languages': ['en'],
            'timezone': 'America/Los_Angeles',
            'geography': 'US',
            'price_min': 800,
            'price_max': 3000,
            'price_model': 'fixed',
            'preferred_maturity': ['mid', 'advanced'],
            'portfolio_urls': ['https://johnsonpr.example.com/press'],
            'evidence_summary': 'Featured clients in major music blogs and publications',
            'proof_strength': 65,
            'source': 'manual',
            'status': 'approved',
            'confidence_score': 70,
        },
        {
            'name': 'Sophie Chen',
            'brand_name': 'Chen Content',
            'website': 'https://chencontent.example.com',
            'email': 'sophie@chencontent.example.com',
            'bio': 'Short-form content creator specializing in TikTok and Reels for pop, indie, and electronic artists. Scripts, editing, and strategy.',
            'genres': ['pop', 'indie', 'electronic'],
            'services': ['short_form_content', 'social_media_strategy'],
            'languages': ['en', 'zh'],
            'timezone': 'America/Los_Angeles',
            'geography': 'Global',
            'price_min': 200,
            'price_max': 800,
            'price_model': 'hourly',
            'preferred_maturity': ['early', 'mid'],
            'portfolio_urls': ['https://chencontent.example.com/videos'],
            'evidence_summary': 'Viral content creator with millions of views',
            'proof_strength': 55,
            'source': 'manual',
            'status': 'approved',
            'confidence_score': 60,
        },
        {
            'name': 'DJ Promo',
            'brand_name': 'DJ Promo Services',
            'website': 'https://djpromo.example.com',
            'email': 'info@djpromo.example.com',
            'bio': 'Release campaign specialist for electronic, EDM, and house music. Pre-save campaigns, launch strategies, and post-release retention.',
            'genres': ['electronic', 'edm', 'house'],
            'services': ['release_campaigns', 'playlist_pitching', 'ads'],
            'languages': ['en'],
            'timezone': 'Europe/London',
            'geography': 'Europe',
            'price_min': 500,
            'price_max': 2000,
            'price_model': 'fixed',
            'preferred_maturity': ['mid', 'advanced'],
            'portfolio_urls': ['https://djpromo.example.com/releases'],
            'evidence_summary': 'Successful launch campaigns for European electronic artists',
            'proof_strength': 50,
            'source': 'manual',
            'status': 'approved',
            'confidence_score': 55,
        },
        {
            'name': 'Luna Martinez',
            'brand_name': 'Luna Growth',
            'website': 'https://lunagrowth.example.com',
            'email': 'luna@lunagrowth.example.com',
            'bio': 'Community growth specialist for Latin pop and reggaeton. Discord communities, email lists, SMS campaigns, and fan engagement.',
            'genres': ['latin-pop', 'reggaeton'],
            'services': ['community_growth', 'social_media_strategy', 'release_campaigns'],
            'languages': ['en', 'es'],
            'timezone': 'America/New_York',
            'geography': 'US',
            'price_min': 400,
            'price_max': 1500,
            'price_model': 'retainer',
            'preferred_maturity': ['early', 'mid'],
            'portfolio_urls': ['https://lunagrowth.example.com/communities'],
            'evidence_summary': 'Built engaged communities for Latin artists',
            'proof_strength': 60,
            'source': 'manual',
            'status': 'approved',
            'confidence_score': 65,
        },
        {
            'name': 'Alex Thompson',
            'brand_name': 'Thompson Analytics',
            'website': 'https://thompsonanalytics.example.com',
            'email': 'alex@thompsonanalytics.example.com',
            'bio': 'Analytics and ads specialist for all genres. Funnel tracking, attribution, KPI reviews, and data-driven optimization.',
            'genres': ['hip-hop', 'pop', 'indie', 'electronic', 'country'],
            'services': ['analytics', 'ads'],
            'languages': ['en'],
            'timezone': 'America/Los_Angeles',
            'geography': 'US',
            'price_min': 600,
            'price_max': 2000,
            'price_model': 'hourly',
            'preferred_maturity': ['mid', 'advanced'],
            'portfolio_urls': ['https://thompsonanalytics.example.com/reports'],
            'evidence_summary': 'Data-driven insights for marketing optimization',
            'proof_strength': 45,
            'source': 'manual',
            'status': 'approved',
            'confidence_score': 50,
        },
        {
            'name': 'Yuki Tanaka',
            'brand_name': 'Tanaka Branding',
            'website': 'https://tanakabranding.example.com',
            'email': 'yuki@tanakabranding.example.com',
            'bio': 'Identity and branding specialist for indie, folk, and alt-rock. Visual identity, EPK creation, and brand positioning.',
            'genres': ['indie', 'folk', 'alt-rock'],
            'services': ['identity_positioning', 'coaching'],
            'languages': ['en', 'ja'],
            'timezone': 'Asia/Tokyo',
            'geography': 'Global',
            'price_min': 350,
            'price_max': 1000,
            'price_model': 'fixed',
            'preferred_maturity': ['early', 'mid'],
            'portfolio_urls': ['https://tanakabranding.example.com/brands'],
            'evidence_summary': 'Created memorable brand identities for indie artists',
            'proof_strength': 40,
            'source': 'manual',
            'status': 'approved',
            'confidence_score': 45,
        },
    ]
    
    for data in marketers_data:
        marketer = Marketer(**data)
        db.session.add(marketer)
    
    db.session.commit()
    print(f"[OK] Seeded {len(marketers_data)} marketers")


def ensure_demo_marketers_seeded():
    """
    If the marketers table is empty, insert the same demo rows as seed_marketers().

    Called automatically on app startup (unless SOUNDMATCH_SKIP_AUTO_SEED is set).
    On PostgreSQL, uses an advisory transaction lock so multiple Gunicorn workers
    do not each insert a full duplicate catalogue on first boot.
    """
    from sqlalchemy import text

    try:
        if Marketer.query.count() > 0:
            return
    except Exception:
        db.session.rollback()
        return

    dialect = db.session.get_bind().dialect.name
    if dialect == "postgresql":
        db.session.execute(text("SELECT pg_advisory_xact_lock(48291001)"))
        try:
            if Marketer.query.count() > 0:
                db.session.rollback()
                return
        except Exception:
            db.session.rollback()
            return

    try:
        seed_marketers()
    except Exception:
        db.session.rollback()
        raise


def seed_briefs():
    """Seed 2 sample campaign briefs."""
    briefs_data = [
        {
            'artist_name': 'Maya',
            'email': 'maya@example.com',
            'genres': ['indie', 'bedroom-pop'],
            'sub_genres': ['lo-fi', 'dream-pop'],
            'goals': ['streams', 'playlist_adds'],
            'services_needed': ['playlist_pitching', 'social_media_strategy'],
            'budget_min': 200,
            'budget_max': 500,
            'spotify_monthly_listeners': 800,
            'tiktok_followers': 3200,
            'ig_followers': 0,
            'yt_subscribers': 0,
            'timezone': 'America/New_York',
            'languages': ['en'],
            'timeline': '1_month',
            'past_marketing_exp': 'diy',
        },
        {
            'artist_name': 'Elena',
            'email': 'elena@example.com',
            'genres': ['latin-pop', 'reggaeton'],
            'sub_genres': ['trap', 'urban'],
            'goals': ['followers', 'streams', 'brand_deals'],
            'services_needed': ['ads', 'pr', 'social_media_strategy', 'release_campaigns'],
            'budget_min': 3000,
            'budget_max': 8000,
            'spotify_monthly_listeners': 220000,
            'tiktok_followers': 0,
            'ig_followers': 85000,
            'yt_subscribers': 12000,
            'timezone': 'America/Los_Angeles',
            'languages': ['en', 'es'],
            'timeline': 'asap',
            'past_marketing_exp': 'hired_before',
        },
    ]
    
    briefs = []
    for data in briefs_data:
        brief = CampaignBrief(**data)
        brief.compute_maturity()
        db.session.add(brief)
        briefs.append(brief)
    
    db.session.commit()
    print(f"[OK] Seeded {len(briefs_data)} campaign briefs")
    
    return briefs


def print_matches(briefs):
    """Print matching results for briefs."""
    print("\n" + "="*80)
    print("MATCHING RESULTS")
    print("="*80)
    
    for brief in briefs:
        print(f"\n[Brief] {brief.artist_name}")
        print(f"   Genres: {', '.join(brief.genres)}")
        print(f"   Maturity: {brief.maturity_tier}")
        print(f"   Budget: ${brief.budget_min}-${brief.budget_max}")
        
        results = rank_marketers(brief, top_n=5)
        
        if results:
            print(f"\n   Top 5 Matches:")
            for i, result in enumerate(results, 1):
                print(f"\n   {i}. {result['marketer']['name']} - Score: {result['match_score']}")
                print(f"      Reasons: {', '.join(result['top_reasons'][:2])}")
        else:
            print("   No matches found")
    
    print("\n" + "="*80)


def main():
    """Main seed function."""
    app = create_app()
    
    with app.app_context():
        # Drop and recreate tables
        print("Creating database tables...")
        db.drop_all()
        db.create_all()
        print("[OK] Database tables created")
        
        # Seed data
        seed_marketers()
        briefs = seed_briefs()
        
        # Print matching results
        print_matches(briefs)
        
        print("\n[OK] Seeding complete!")


if __name__ == '__main__':
    main()

