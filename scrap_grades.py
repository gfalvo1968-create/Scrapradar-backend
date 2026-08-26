"""Scrap Radar scrap-grade conversion layer.

Converts market reference prices into configurable estimated scrap-grade values.
These are starting-point estimates only. Local yard quotes should eventually
replace or calibrate these factors by location and buyer.
"""

COPPER_GRADE_FACTORS = {
    "bare_bright": {"label": "Bare Bright Copper", "factor": 0.96},
    "copper_1": {"label": "#1 Copper", "factor": 0.92},
    "copper_2": {"label": "#2 Copper", "factor": 0.86},
    "copper_3": {"label": "#3 / Light Copper", "factor": 0.74},
    "insulated_1": {"label": "#1 Insulated Copper Wire", "factor": 0.68},
    "insulated_2": {"label": "#2 Insulated Copper Wire", "factor": 0.52},
    "insulated_3": {"label": "#3 Insulated Copper Wire", "factor": 0.34},
}


def estimate_copper_grades(copper_market_price):
    try:
        market = float(copper_market_price)
    except (TypeError, ValueError):
        return {}

    if market <= 0:
        return {}

    grades = {}
    for key, item in COPPER_GRADE_FACTORS.items():
        grades[key] = {
            "label": item["label"],
            "estimated_price_per_lb": round(market * item["factor"], 2),
            "market_factor": item["factor"],
            "basis": "copper market reference",
        }
    return grades
