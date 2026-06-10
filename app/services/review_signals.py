"""Extract third-party review signals from fetched page text."""
import re


def extract_review_signals(corpus):
    """
    Return rating (0-5), review_count, source_label from page text.
    Supports common patterns on agency sites and directories.
    """
    text = (corpus or "").lower()
    rating = 0.0
    reviews = 0
    source = ""

    patterns = [
        (r"([1-5](?:\.[0-9])?)\s*/\s*5", "page"),
        (r"([4-5](?:\.[0-9])?)\s*out of\s*5", "page"),
        (r"clutch\s*rating[^\d]*([1-5](?:\.[0-9])?)", "clutch"),
        (r"google\s*rating[^\d]*([1-5](?:\.[0-9])?)", "google"),
        (r"trustpilot[^\d]*([1-5](?:\.[0-9])?)", "trustpilot"),
    ]
    for pattern, label in patterns:
        match = re.search(pattern, text)
        if match:
            rating = max(rating, float(match.group(1)))
            source = source or label

    review_match = re.search(r"([0-9]{1,4})\s+reviews?", text)
    if review_match:
        reviews = int(review_match.group(1))

    clutch_reviews = re.search(r"(\d+)\s+clutch\s+reviews?", text)
    if clutch_reviews:
        reviews = max(reviews, int(clutch_reviews.group(1)))
        source = source or "clutch"

    return rating, reviews, source
