import ast
from pathlib import Path


def test_streamlit_workspace_exposes_multi_quote_procurement_flow():
    source = Path("streamlit_app.py").read_text(encoding="utf-8")
    module = ast.parse(source)

    top_level_functions = {
        node.name: node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "_render_comparison_workspace" in top_level_functions
    assert "_render_market_context" in top_level_functions
    assert "_render_risks" in top_level_functions
    assert "main" in top_level_functions

    main_source = ast.get_source_segment(source, top_level_functions["main"])
    assert "accept_multiple_files=True" in main_source
    assert '"Compare"' in main_source
    assert '"Market Context"' in main_source
    assert "weights=weight_values" in main_source
    assert "do_market=do_market" in main_source
    assert "market_query=market_query.strip()" in main_source

    assert '"Highest weighted score"' in source
    assert '"ALTERNATIVE BIDS"' in source
    assert '"DECISION CONSIDERATIONS"' in source
    assert '"BEFORE AWARDING"' in source
