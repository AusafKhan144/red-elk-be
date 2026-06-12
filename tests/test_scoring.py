"""Unit tests for the pure scoring service."""
import pytest

from app.services.scoring import accessible_question_count, score_responses


def _resp(qid: str, dim: str, value: float) -> dict:
    return {"question_id": qid, "dimension_id": dim, "answer_value": value}


# ── tier filtering ───────────────────────────────────────────────────────────

def test_accessible_question_count_per_tier(config):
    assert accessible_question_count(config, "free") == 4      # 2 per dimension
    assert accessible_question_count(config, "basic") == 8     # 4 per dimension
    assert accessible_question_count(config, "premium") == 10  # all

def test_accessible_question_count_empty_config():
    assert accessible_question_count({}, "free") == 0


def test_premium_questions_ignored_for_free_tier(config):
    # s3..s5 are above free tier — answering them must not affect the score
    responses = [_resp("s1", "strategy", 5), _resp("s2", "strategy", 5),
                 _resp("s5", "strategy", 1)]
    result = score_responses(responses, config, "free")
    assert result.dimension_scores["strategy"] == 100.0


def test_premium_tier_includes_all_questions(config):
    responses = [_resp(f"s{i}", "strategy", 5) for i in range(1, 5)] + [_resp("s5", "strategy", 0)]
    result = score_responses(responses, config, "premium")
    assert result.dimension_scores["strategy"] == pytest.approx(80.0)


# ── dimension and overall scoring ────────────────────────────────────────────

def test_dimension_score_is_mean_of_answered(config):
    # s1=5 → 100, s2=3 → 60 → mean 80
    responses = [_resp("s1", "strategy", 5), _resp("s2", "strategy", 3)]
    result = score_responses(responses, config, "free")
    assert result.dimension_scores["strategy"] == pytest.approx(80.0)
    # no answers for "data" → 0
    assert result.dimension_scores["data"] == 0.0


def test_overall_is_weighted_average(config):
    # strategy: (100+60)/2 = 80, data: (20+40)/2 = 30
    responses = [
        _resp("s1", "strategy", 5), _resp("s2", "strategy", 3),
        _resp("d1", "data", 1), _resp("d2", "data", 2),
    ]
    result = score_responses(responses, config, "free")
    # 80*0.6 + 30*0.4 = 60
    assert result.overall_score == pytest.approx(60.0)
    assert result.tier_result == "maturing"


def test_no_responses_scores_zero(config):
    result = score_responses([], config, "free")
    assert result.overall_score == 0.0
    assert result.tier_result == "nascent"


# ── threshold classification ─────────────────────────────────────────────────

@pytest.mark.parametrize("answers, expected", [
    ((1, 1, 1, 1), "nascent"),      # all 20 → overall 20
    ((3, 2, 2, 2), "developing"),   # strategy 50, data 40 → 46
    ((4, 3, 3, 3), "maturing"),     # strategy 70, data 60 → 66
    ((5, 5, 5, 4), "leading"),      # strategy 100, data 90 → 96
])
def test_tier_classification(config, answers, expected):
    s1, s2, d1, d2 = answers
    responses = [
        _resp("s1", "strategy", s1), _resp("s2", "strategy", s2),
        _resp("d1", "data", d1), _resp("d2", "data", d2),
    ]
    result = score_responses(responses, config, "free")
    assert result.tier_result == expected


def test_boundary_scores(config):
    # max score lands exactly on 100 — must classify as leading, not fall through
    responses = [_resp(q, d, 5) for q, d in
                 [("s1", "strategy"), ("s2", "strategy"), ("d1", "data"), ("d2", "data")]]
    result = score_responses(responses, config, "free")
    assert result.overall_score == 100.0
    assert result.tier_result == "leading"


# ── recommendations ──────────────────────────────────────────────────────────

def test_recommendations_match_tier_result(config):
    responses = [
        _resp("s1", "strategy", 5), _resp("s2", "strategy", 3),
        _resp("d1", "data", 1), _resp("d2", "data", 2),
    ]
    result = score_responses(responses, config, "free")  # maturing
    assert result.recommendations == {
        "strategy": "strategy-maturing",
        "data": "data-maturing",
    }


def test_recommendations_empty_when_missing_from_config(config):
    config["scoring"].pop("recommendations")
    result = score_responses([_resp("s1", "strategy", 5)], config, "free")
    assert result.recommendations == {"strategy": "", "data": ""}
