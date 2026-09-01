"""Scrap Radar material catalog and pricing framework.

The catalog separates three different kinds of price information:
1. market_reference: exchange/benchmark context,
2. derived_estimate: a transparent estimate tied to a benchmark,
3. local_quote: yard/refiner/buyer pricing that must come from a real quote.

This prevents Scrap Radar from presenting commodity benchmarks as guaranteed
scrap-yard payouts. Every grade has a stable ID so local quotes can later be
stored by buyer, location, date, and unit.
"""

LB_PER_METRIC_TON = 2204.62262185

MATERIAL_CATALOG = {
    "precious_metals": [
        {"id": "gold", "label": "Gold", "unit": "troy_oz", "pricing_mode": "market_reference", "reference": "gold"},
        {"id": "silver", "label": "Silver", "unit": "troy_oz", "pricing_mode": "market_reference", "reference": "silver"},
        {"id": "platinum", "label": "Platinum", "unit": "troy_oz", "pricing_mode": "market_reference", "reference": "platinum"},
        {"id": "palladium", "label": "Palladium", "unit": "troy_oz", "pricing_mode": "market_reference", "reference": "palladium"},
        {"id": "rhodium", "label": "Rhodium", "unit": "troy_oz", "pricing_mode": "local_quote", "quote_type": "refiner"},
    ],
    "copper": [
        {"id": "bare_bright", "label": "Bare Bright Copper", "unit": "lb", "pricing_mode": "derived_estimate", "reference": "copper", "factor": 0.96},
        {"id": "copper_1", "label": "#1 Copper", "unit": "lb", "pricing_mode": "derived_estimate", "reference": "copper", "factor": 0.92},
        {"id": "copper_2", "label": "#2 Copper", "unit": "lb", "pricing_mode": "derived_estimate", "reference": "copper", "factor": 0.86},
        {"id": "copper_3", "label": "#3 / Light Copper", "unit": "lb", "pricing_mode": "derived_estimate", "reference": "copper", "factor": 0.74},
        {"id": "insulated_1", "label": "#1 Insulated Copper Wire", "unit": "lb", "pricing_mode": "derived_estimate", "reference": "copper", "factor": 0.68},
        {"id": "insulated_2", "label": "#2 Insulated Copper Wire", "unit": "lb", "pricing_mode": "derived_estimate", "reference": "copper", "factor": 0.52},
        {"id": "insulated_3", "label": "#3 Insulated Copper Wire", "unit": "lb", "pricing_mode": "derived_estimate", "reference": "copper", "factor": 0.34},
        {"id": "romex", "label": "Romex / House Wire", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "thhn", "label": "THHN / High Recovery Wire", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "copper_tubing", "label": "Copper Tubing", "unit": "lb", "pricing_mode": "local_quote"},
    ],
    "brass": [
        {"id": "yellow_brass", "label": "Yellow Brass", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "red_brass", "label": "Red Brass", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "semi_red_brass", "label": "Semi-Red Brass", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "brass_shells", "label": "Clean Brass Shells", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "dirty_brass", "label": "Dirty / Mixed Brass", "unit": "lb", "pricing_mode": "local_quote"},
    ],
    "aluminum": [
        {"id": "aluminum_clean_extrusion", "label": "Clean Aluminum Extrusion", "unit": "lb", "pricing_mode": "local_quote", "reference": "aluminum"},
        {"id": "aluminum_painted_extrusion", "label": "Painted / Coated Extrusion", "unit": "lb", "pricing_mode": "local_quote", "reference": "aluminum"},
        {"id": "aluminum_sheet", "label": "Clean Sheet Aluminum", "unit": "lb", "pricing_mode": "local_quote", "reference": "aluminum"},
        {"id": "aluminum_cast", "label": "Cast Aluminum", "unit": "lb", "pricing_mode": "local_quote", "reference": "aluminum"},
        {"id": "aluminum_siding", "label": "Aluminum Siding", "unit": "lb", "pricing_mode": "local_quote", "reference": "aluminum"},
        {"id": "aluminum_coated", "label": "Coated / Painted Aluminum", "unit": "lb", "pricing_mode": "local_quote", "reference": "aluminum"},
        {"id": "aluminum_wire", "label": "Clean Aluminum Wire", "unit": "lb", "pricing_mode": "local_quote", "reference": "aluminum"},
        {"id": "aluminum_rims", "label": "Clean Aluminum Rims", "unit": "lb", "pricing_mode": "local_quote", "reference": "aluminum"},
        {"id": "aluminum_radiator", "label": "Aluminum Radiator", "unit": "lb", "pricing_mode": "local_quote", "reference": "aluminum"},
        {"id": "copper_aluminum_radiator", "label": "Copper/Aluminum Radiator", "unit": "lb", "pricing_mode": "local_quote"},
    ],
    "stainless": [
        {"id": "stainless_304", "label": "304 Stainless", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "stainless_316", "label": "316 Stainless", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "stainless_mixed", "label": "Mixed / Unknown Stainless", "unit": "lb", "pricing_mode": "local_quote"},
    ],
    "lead_zinc_nickel": [
        {"id": "clean_lead", "label": "Clean Lead", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "lead_wheel_weights", "label": "Lead Wheel Weights", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "zinc_die_cast", "label": "Zinc / Die Cast", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "nickel_alloy", "label": "Nickel Alloy", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "tin", "label": "Tin", "unit": "lb", "pricing_mode": "local_quote"},
    ],
    "ferrous": [
        {"id": "prepared_steel", "label": "Prepared Steel", "unit": "ton", "pricing_mode": "local_quote"},
        {"id": "unprepared_steel", "label": "Unprepared Steel", "unit": "ton", "pricing_mode": "local_quote"},
        {"id": "light_iron", "label": "Light Iron / Shred", "unit": "ton", "pricing_mode": "local_quote"},
        {"id": "cast_iron", "label": "Cast Iron", "unit": "ton", "pricing_mode": "local_quote"},
        {"id": "hms_1", "label": "HMS #1", "unit": "ton", "pricing_mode": "local_quote"},
        {"id": "hms_2", "label": "HMS #2", "unit": "ton", "pricing_mode": "local_quote"},
        {"id": "rebar", "label": "Rebar", "unit": "ton", "pricing_mode": "local_quote"},
        {"id": "white_goods", "label": "White Goods / Appliances", "unit": "ton", "pricing_mode": "local_quote"},
    ],
    "motors_transformers": [
        {"id": "electric_motors", "label": "Electric Motors", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "transformers", "label": "Transformers", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "sealed_units", "label": "Sealed Units / Compressors", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "ballasts", "label": "Ballasts", "unit": "lb", "pricing_mode": "local_quote"},
    ],
    "batteries": [
        {"id": "lead_acid_battery", "label": "Lead-Acid Battery", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "lithium_battery", "label": "Lithium-Ion Battery", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "nimh_battery", "label": "NiMH Battery", "unit": "lb", "pricing_mode": "local_quote"},
    ],
    "electronics": [
        {"id": "board_high", "label": "High Grade Circuit Boards", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "board_mid", "label": "Mid Grade Circuit Boards", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "board_low", "label": "Low Grade Circuit Boards", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "ram", "label": "RAM", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "cpu", "label": "CPUs / Processors", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "hard_drives", "label": "Hard Drives", "unit": "lb", "pricing_mode": "local_quote"},
        {"id": "power_supplies", "label": "Power Supplies", "unit": "lb", "pricing_mode": "local_quote"},
    ],
    "catalytic": [
        {"id": "catalytic_converter", "label": "Catalytic Converter", "unit": "each", "pricing_mode": "local_quote", "quote_type": "serial_or_assay"},
    ],
}

CATEGORY_LABELS = {
    "precious_metals": "Precious Metals",
    "copper": "Copper",
    "brass": "Brass",
    "aluminum": "Aluminum",
    "stainless": "Stainless Steel",
    "lead_zinc_nickel": "Lead / Zinc / Nickel / Tin",
    "ferrous": "Ferrous Steel & Iron",
    "motors_transformers": "Motors & Transformers",
    "batteries": "Batteries",
    "electronics": "Electronics / E-Scrap",
    "catalytic": "Catalytic Converters",
}


def _benchmark_value(reference, metals):
    metal = metals.get(reference) or {}
    price = metal.get("price")
    if price is None:
        return None, metal.get("unit")

    if reference == "aluminum":
        return round(float(price) / LB_PER_METRIC_TON, 4), "lb"

    return float(price), metal.get("unit")


def build_material_pricing(metals):
    """Return the catalog with current benchmark/estimate context attached."""
    categories = []

    for category_id, materials in MATERIAL_CATALOG.items():
        priced_materials = []
        for material in materials:
            row = dict(material)
            reference = row.get("reference")
            benchmark_price = None
            benchmark_unit = None

            if reference:
                benchmark_price, benchmark_unit = _benchmark_value(reference, metals)
                row["benchmark_price"] = benchmark_price
                row["benchmark_unit"] = benchmark_unit

            if row["pricing_mode"] == "market_reference":
                row["price"] = benchmark_price
                row["price_unit"] = benchmark_unit
                row["price_type"] = "market_reference"
            elif row["pricing_mode"] == "derived_estimate" and benchmark_price is not None:
                row["price"] = round(benchmark_price * float(row["factor"]), 2)
                row["price_unit"] = "lb"
                row["price_type"] = "estimated_scrap_grade"
            else:
                row["price"] = None
                row["price_unit"] = row["unit"]
                row["price_type"] = "local_quote_required"

            priced_materials.append(row)

        categories.append({
            "id": category_id,
            "label": CATEGORY_LABELS[category_id],
            "materials": priced_materials,
        })

    return categories
