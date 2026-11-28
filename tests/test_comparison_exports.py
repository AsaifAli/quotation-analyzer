from io import BytesIO, StringIO

import pandas as pd
from openpyxl import load_workbook

from modules.report import analysis_xlsx, quotations_csv


def test_excel_export_includes_supplier_item_and_reconciliation_sheets():
    result = {
        "scores": [],
        "validation": [],
        "risks": [],
        "quotations": [],
        "comparison_matrix": {
            "suppliers": [{"quote_label": "Contoso — A-100", "supplier": "Contoso"}],
            "line_items": [{"description": "Industrial router"}],
            "pricing_reconciliation": [{"quote_label": "Contoso — A-100", "status": "matched"}],
        },
    }

    workbook = load_workbook(BytesIO(analysis_xlsx(result)), read_only=True)

    assert {
        "Scores",
        "Validation",
        "Risks",
        "Quotations",
        "Supplier Comparison",
        "Line Items",
        "Price Reconciliation",
    }.issubset(set(workbook.sheetnames))


def test_supplier_csv_preserves_quote_identity_and_commercial_terms():
    result = {
        "quotations": [
            {
                "supplier": "Contoso",
                "quote_reference": "A-100",
                "source_document": "contoso-a.pdf",
                "total_cost": 100000,
                "currency": "INR",
                "subtotal": 90000,
                "tax_amount": 10000,
                "tax_included": True,
                "shipping_cost": 500,
                "discount_amount": 1000,
                "additional_charges": 0,
                "payment_terms": "30% advance",
                "warranty": "2 years",
                "support": "24x7",
                "exclusions": ["Installation"],
            }
        ]
    }

    frame = pd.read_csv(StringIO(quotations_csv(result)))

    assert frame.loc[0, "quote_reference"] == "A-100"
    assert frame.loc[0, "source_document"] == "contoso-a.pdf"
    assert frame.loc[0, "tax_amount"] == 10000
    assert frame.loc[0, "payment_terms"] == "30% advance"
    assert frame.loc[0, "warranty"] == "2 years"
    assert frame.loc[0, "exclusions"] == "Installation"
