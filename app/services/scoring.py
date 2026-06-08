"""
Pure scoring functions — no DB access, no side effects.
Input: responses list + assessment config dict + user tier.
Output: ScoringResult with dimension scores, overall score, tier classification,
        radar data, and per-dimension recommendations.
"""
from dataclasses import dataclass

# Tier hierarchy used for question filtering
_TIER_ORDER = {"free": 0, "basic": 1, "premium": 2}

# Questions accessible per tier (2 per dim for free, 4 for basic, all for premium)
_TIER_LIMITS = {"free": 2, "basic": 4, "premium": None}


@dataclass
class ScoringResult:
    dimension_scores: dict  # {dimension_id: float (0-100)}
    dimension_names: dict   # {dimension_id: str}
    overall_score: float    # 0-100
    tier_result: str        # nascent | developing | maturing | leading
    recommendations: dict   # {dimension_id: str}


def score_responses(responses: list[dict], config: dict, tier: str) -> ScoringResult:
    """
    Args:
        responses: [{"question_id": str, "dimension_id": str, "answer_value": float}, ...]
        config:    assessment config dict from JSONB (dimensions, scoring keys)
        tier:      user's tier snapshotted at session start
    Returns:
        ScoringResult
    """
    response_map = {r["question_id"]: float(r["answer_value"]) for r in responses}

    dimension_scores = {}
    dimension_names = {}
    dimension_weights = {}

    for dim in config.get("dimensions", []):
        dim_id = dim["id"]
        dimension_names[dim_id] = dim["name"]
        dimension_weights[dim_id] = float(dim.get("weight", 1.0))

        eligible_questions = _filter_questions_by_tier(dim.get("questions", []), tier)
        if not eligible_questions:
            dimension_scores[dim_id] = 0.0
            continue

        scored = []
        for q in eligible_questions:
            raw = response_map.get(q["id"])
            if raw is not None:
                scored.append(_score_question(raw, q))

        dimension_scores[dim_id] = (sum(scored) / len(scored)) if scored else 0.0

    overall = _weighted_average(dimension_scores, dimension_weights)
    thresholds = config.get("scoring", {}).get("thresholds", _default_thresholds())
    tier_result = _classify_tier(overall, thresholds)
    recommendations = _pick_recommendations(dimension_scores, tier_result, config)

    return ScoringResult(
        dimension_scores=dimension_scores,
        dimension_names=dimension_names,
        overall_score=round(overall, 2),
        tier_result=tier_result,
        recommendations=recommendations,
    )


def _filter_questions_by_tier(questions: list[dict], tier: str) -> list[dict]:
    """Return questions accessible at this tier, capped per the tier limit."""
    user_level = _TIER_ORDER.get(tier, 0)
    eligible = [
        q for q in questions
        if _TIER_ORDER.get(q.get("tier", "free"), 0) <= user_level
    ]
    limit = _TIER_LIMITS.get(tier)
    return eligible if limit is None else eligible[:limit]


def _score_question(answer_value: float, question: dict) -> float:
    """Normalise a single answer to 0–100."""
    q_type = question.get("type", "scale")
    max_score = float(question.get("max_score", 5))

    if q_type == "scale":
        return min(max(answer_value / max_score * 100, 0), 100)

    if q_type == "boolean":
        return 100.0 if answer_value else 0.0

    if q_type == "multiple_choice":
        options = question.get("options", {})
        scoring_map = options.get("scoring", {}) if isinstance(options, dict) else {}
        key = str(int(answer_value))
        raw = scoring_map.get(key, 0.5)
        return float(raw) * 100

    # text: partial credit for non-empty (encoded as 1 = provided, 0 = skipped)
    return 50.0 if answer_value else 0.0


def _weighted_average(scores: dict, weights: dict) -> float:
    total_weight = sum(weights.get(k, 1.0) for k in scores)
    if total_weight == 0:
        return 0.0
    return sum(scores[k] * weights.get(k, 1.0) for k in scores) / total_weight


def _classify_tier(overall_score: float, thresholds: dict) -> str:
    """
    thresholds: {"nascent": [0, 30], "developing": [30, 55], ...}
    Returns the label whose range contains overall_score.
    Fallback: "nascent".
    """
    for label, bounds in thresholds.items():
        lo, hi = bounds
        if lo <= overall_score <= hi:
            return label
    return "nascent"


def _pick_recommendations(dimension_scores: dict, tier_result: str, config: dict) -> dict:
    """Pull recommendation text from config.scoring.recommendations[dim_id][tier_result]."""
    rec_config = config.get("scoring", {}).get("recommendations", {})
    return {
        dim_id: rec_config.get(dim_id, {}).get(tier_result, "")
        for dim_id in dimension_scores
    }


def _default_thresholds() -> dict:
    return {
        "nascent": [0, 30],
        "developing": [30, 55],
        "maturing": [55, 75],
        "leading": [75, 100],
    }
