from modules.models import normalize_extraction_payload
from modules.scoring import build_comparison_matrix, score_quotations


def test_normalize_extraction_preserves_itemized_prices_and_commercial_terms():
    result = normalize_extraction_payload({
        "quotations": [{
            "supplier": "Northwind",
            "grand_total": "₹1,18,000",
            "subtotal": "100000",
            "tax": "18000",
            "tax_included": "No",
            "shipping": "2500",
            "payment_schedule": "30% advance, 70% on acceptance",
            "warranty_period": "24 months",
            "not_included": ["Civil works"],
            "line_items": [{
                "item": "Industrial printer",
                "qty": "2",
                "unit": "units",
                "rate": "₹40,000",
                "line_total": "₹80,000",
            }],
        }]
    })
    quotation = result["quotations"][0]
    assert quotation["total_cost"] == 118000
    assert quotation["currency"] == "INR"
    assert quotation["subtotal"] == 100000
    assert quotation["tax_amount"] == 18000
    assert quotation["tax_included"] is False
    assert quotation["shipping_cost"] == 2500
    assert quotation["payment_terms"] == "30% advance, 70% on acceptance"
    assert quotation["warranty"] == "24 months"
    assert quotation["exclusions"] == ["Civil works"]
    assert quotation["line_items"][0] == {
        "description": "Industrial printer",
        "quantity": 2.0,
        "unit": "units",
        "unit_price": 40000.0,
        "total_price": 80000.0,
        "notes": None,
    }


def test_comparison_matrix_aligns_identical_items_and_labels_unlisted_scope():
    quotations = [
        {
            "supplier": "Northwind",
            "currency": "INR",
            "total_cost": 118000,
            "subtotal": 100000,
            "tax_amount": 18000,
            "shipping_cost": 0,
            "discount_amount": 0,
            "additional_charges": 0,
            "line_items": [
                {"description": "Industrial printer", "quantity": 2, "unit": "units", "unit_price": 40000, "total_price": 80000}
            ],
        },
        {
            "supplier": "Contoso",
            "currency": "INR",
            "total_cost": 125000,
            "line_items": [
                {"description": "Industrial printer", "quantity": 2, "unit": "units", "unit_price": 42000, "total_price": 84000},
                {"description": "Installation", "quantity": 1, "unit": "service", "unit_price": 5000, "total_price": 5000},
            ],
        },
    ]
    matrix = build_comparison_matrix(quotations, score_quotations(quotations))
    assert matrix["cost_comparable"] is True
    printer = next(item for item in matrix["line_items"] if item["description"] == "Industrial printer")
    assert printer["unit_price_comparable"] is True
    assert printer["lowest_unit_price"] == 40000
    assert printer["not_listed_by"] == []
    installation = next(item for item in matrix["line_items"] if item["description"] == "Installation")
    assert installation["not_listed_by"] == ["Northwind"]
    assert matrix["pricing_reconciliation"][0]["status"] == "matched"


def test_comparison_matrix_never_converts_or_compares_different_currencies():
    quotations = [
        {"supplier": "Northwind", "currency": "INR", "total_cost": 100000},
        {"supplier": "Contoso", "currency": "USD", "total_cost": 1200},
    ]
    matrix = build_comparison_matrix(quotations)
    assert matrix["cost_comparable"] is False
    assert matrix["lowest_price_supplier"] is None
    assert all(item["price_difference_from_lowest"] is None for item in matrix["suppliers"])
