import re
from typing import Optional


def _compute_weighted_scores(
    results: list[dict], 
    sustainability_weight: float = 0.5, 
    price_weight: float = 0.3,
    locality_weight: float = 0.2
) -> list[dict]:
    scored_candidates: list[dict] = []
    repair_entries: list[dict] = []

    for item in results:
        if item.get("repair_suggestion"):
            item["sustainability_score"] = 0.0
            item["price_score"] = 0.0
            item["locality_score"] = 0.0
            item["final_score"] = 0.0
            repair_entries.append(item)
            continue
        scored_candidates.append(item)

    if not scored_candidates:
        return repair_entries

    carbon_values = [_extract_number(i.get("carbon_saved", "")) for i in scored_candidates]
    price_values = [_extract_number(i.get("price", "")) for i in scored_candidates]

    known_carbon = [v for v in carbon_values if v is not None]
    known_prices = [v for v in price_values if v is not None]

    carbon_min = min(known_carbon) if known_carbon else 0.0
    carbon_max = max(known_carbon) if known_carbon else 0.0
    price_min = min(known_prices) if known_prices else 0.0
    price_max = max(known_prices) if known_prices else 0.0

    for item, carbon, price in zip(scored_candidates, carbon_values, price_values):
        # 1. Sustainability Score (Carbon)
        if carbon is None or carbon_max == carbon_min:
            sustainability_score = 1.0 if carbon is not None else 0.0
        else:
            sustainability_score = (carbon - carbon_min) / (carbon_max - carbon_min)

        # 2. Price Score (Inverse - cheaper is better)
        if price is None or price_max == price_min:
            price_score = 1.0 if price is not None else 0.0
        else:
            price_score = (price_max - price) / (price_max - price_min)

        # 3. Locality Score (Binary bonus for now)
        locality_score = 1.0 if item.get("is_local_business") else 0.0

        # Weighted Final Score
        final_score = (
            (sustainability_weight * sustainability_score) + 
            (price_weight * price_score) + 
            (locality_weight * locality_score)
        )

        item["sustainability_score"] = round(sustainability_score, 2)
        item["price_score"] = round(price_score, 2)
        item["locality_score"] = round(locality_score, 2)
        item["final_score"] = str(round(final_score * 10, 2))

    scored_candidates.sort(
        key=lambda i: (i.get("final_score", 0.0), i.get("sustainability_score", 0.0), i.get("price_score", 0.0)),
        reverse=True,
    )
    return scored_candidates + repair_entries

def _extract_number(raw: str) -> Optional[float]:
    if not raw:
        return None
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", raw)
    if not match:
        return None
    return float(match.group(0).replace(",", ""))