import re
from io import BytesIO

import openpyxl

_TIER_LEVELS = {"free", "basic", "premium"}
_TIERS_DEFAULT = ["nascent", "developing", "maturing", "leading"]
_SCORING_THRESHOLDS = {
    "nascent": [0, 30],
    "developing": [30, 55],
    "maturing": [55, 75],
    "leading": [75, 100],
}
_DIM_LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def parse_xlsx_to_assessment_config(
    file_bytes: bytes,
    slug: str,
    name: str,
    version: int = 1,
    is_published: bool = False,
    description: str = "",
) -> dict:
    wb = openpyxl.load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(min_row=2, values_only=True))

    # Deduplicate by (dimension_name, question_number) — last occurrence wins (complete row)
    seen: dict[tuple, list] = {}
    for row in rows:
        if not row[0] or row[2] is None:
            continue
        key = (str(row[0]).strip(), int(row[2]))
        seen[key] = list(row)

    # Group into ordered dict of {dim_name: [rows...]}
    dimensions_raw: dict[str, list[list]] = {}
    for (dim_name, _q_num), row in seen.items():
        dimensions_raw.setdefault(dim_name, []).append(row)

    # Sort questions within each dimension by question number
    for rows_list in dimensions_raw.values():
        rows_list.sort(key=lambda r: int(r[2]))

    num_dims = len(dimensions_raw)
    base_weight = round(1.0 / num_dims, 4)
    # Remainder goes to last dimension so weights sum to 1.0
    last_weight = round(1.0 - base_weight * (num_dims - 1), 4)

    dimensions = []
    recommendations: dict[str, dict[str, str]] = {}

    for i, (dim_name, dim_rows) in enumerate(dimensions_raw.items()):
        dim_id = _slugify(dim_name)
        dim_letter = _DIM_LETTERS[i] if i < len(_DIM_LETTERS) else f"d{i}"
        weight = last_weight if i == num_dims - 1 else base_weight

        questions = []
        for row in dim_rows:
            # Columns: dim, category, #, question, response_type, response_options,
            #          rating_guide, rating1, rating2, rating3, rating4, rating5, tier
            q_num = int(row[2])
            q_text = str(row[3]).strip() if row[3] else ""
            tier_raw = str(row[12]).strip().lower() if row[12] else "free"
            tier = tier_raw if tier_raw in _TIER_LEVELS else "free"

            labels = {}
            for idx, col in enumerate(range(7, 12), start=1):
                val = row[col]
                labels[str(idx)] = str(val).strip() if val else ""

            questions.append({
                "id": f"{dim_letter}{q_num}",
                "text": q_text,
                "tier": tier,
                "type": "scale",
                "options": {"min": 1, "max": 5, "labels": labels},
                "max_score": 5,
            })

        dimensions.append({
            "id": dim_id,
            "name": dim_name,
            "weight": weight,
            "questions": questions,
        })

        recommendations[dim_id] = {t: "" for t in _TIERS_DEFAULT}

    return {
        "slug": slug,
        "name": name,
        "description": description,
        "version": version,
        "is_published": is_published,
        "dimensions": dimensions,
        "scoring": {
            "thresholds": _SCORING_THRESHOLDS,
            "recommendations": recommendations,
        },
    }
