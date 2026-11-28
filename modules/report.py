"""Export procurement analysis and comparison reports."""
from __future__ import annotations

import io
import json
from typing import Any, Mapping

import pandas as pd


def _joined(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "; ".join(str(item) for item in value if item is not None)
    return str(value)


def quotations_csv(result: Mapping[str, Any]) -> str:
    """Export one row per quotation, preserving quote and supplier identity."""
    rows = []
    for quote in result.get("quotations", []) or []:
        rows.append({
            "supplier": quote.get("supplier"),
            "quote_reference": quote.get("quote_reference"),
            "source_document": quote.get("source_document"),
            "total_cost": quote.get("total_cost"),
            "currency": quote.get("currency"),
            "subtotal": quote.get("subtotal"),
            "tax_amount": quote.get("tax_amount"),
            "tax_included": quote.get("tax_included"),
            "shipping_cost": quote.get("shipping_cost"),
            "discount_amount": quote.get("discount_amount"),
            "additional_charges": quote.get("additional_charges"),
            "delivery_timeline": quote.get("delivery_timeline"),
            "validity_period": quote.get("validity_period"),
            "payment_terms": quote.get("payment_terms") or quote.get("terms_conditions"),
            "warranty": quote.get("warranty"),
            "support": quote.get("support"),
            "exclusions": _joined(quote.get("exclusions")),
            "line_item_count": len(quote.get("line_items") or []),
        })
    return pd.DataFrame(rows).to_csv(index=False)


def analysis_json(result: Mapping[str, Any]) -> str:
    return json.dumps(result, indent=2, default=str)


def _line_item_rows(matrix: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in matrix.get("line_items", []) or []:
        offers = item.get("offers", []) or []
        if not offers:
            rows.append({
                "item": item.get("description"),
                "quote_label": "",
                "supplier": "",
                "quantity": None,
                "unit": "",
                "unit_price": None,
                "total_price": None,
                "currency": "",
                "notes": "",
                "unit_price_comparable": item.get("unit_price_comparable"),
                "lowest_unit_price": item.get("lowest_unit_price"),
                "highest_unit_price": item.get("highest_unit_price"),
                "not_listed_by": _joined(item.get("not_listed_by")),
            })
            continue
        for offer in offers:
            rows.append({
                "item": item.get("description"),
                "quote_label": offer.get("quote_label"),
                "supplier": offer.get("supplier"),
                "quote_reference": offer.get("quote_reference"),
                "source_document": offer.get("source_document"),
                "quantity": offer.get("quantity"),
                "unit": offer.get("unit"),
                "unit_price": offer.get("unit_price"),
                "total_price": offer.get("total_price"),
                "currency": offer.get("currency"),
                "notes": offer.get("notes"),
                "unit_price_comparable": item.get("unit_price_comparable"),
                "lowest_unit_price": item.get("lowest_unit_price"),
                "highest_unit_price": item.get("highest_unit_price"),
                "not_listed_by": _joined(item.get("not_listed_by")),
            })
    return rows


def analysis_xlsx(result: Mapping[str, Any]) -> bytes:
    """Build a workbook with dedicated supplier, scope and price-check sheets."""
    out = io.BytesIO()
    matrix = result.get("comparison_matrix") or {}
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        pd.DataFrame(result.get("scores", [])).to_excel(
            writer, index=False, sheet_name="Scores"
        )
        pd.DataFrame(result.get("validation", [])).to_excel(
            writer, index=False, sheet_name="Validation"
        )
        pd.DataFrame(result.get("risks", [])).to_excel(
            writer, index=False, sheet_name="Risks"
        )
        pd.DataFrame(result.get("quotations", [])).drop(
            columns=["evidence"], errors="ignore"
        ).to_excel(writer, index=False, sheet_name="Quotations")
        pd.DataFrame(matrix.get("suppliers", [])).to_excel(
            writer, index=False, sheet_name="Supplier Comparison"
        )
        pd.DataFrame(_line_item_rows(matrix)).to_excel(
            writer, index=False, sheet_name="Line Items"
        )
        pd.DataFrame(matrix.get("pricing_reconciliation", [])).to_excel(
            writer, index=False, sheet_name="Price Reconciliation"
        )
        pd.DataFrame(
            [
                {"criterion": key, "normalized_weight": value}
                for key, value in (result.get("weights") or {}).items()
            ]
        ).to_excel(writer, index=False, sheet_name="Scoring Weights")

        market = result.get("market") or {}
        insights = market.get("insights") or {}
        market_rows = [
            {
                "query": market.get("query"),
                "status": insights.get("status"),
                "title": item.get("title"),
                "content": item.get("content"),
                "url": item.get("url"),
            }
            for item in (insights.get("results") or [])
            if isinstance(item, dict)
        ]
        if market_rows:
            pd.DataFrame(market_rows).to_excel(
                writer, index=False, sheet_name="Market Context"
            )
    return out.getvalue()
