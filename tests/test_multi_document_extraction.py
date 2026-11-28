from modules.ai_agent import AgentState, QuotationIntelligenceAgent


class _FiveDocumentProcessor:
    def extract(self, path):
        source = path.rsplit("/", 1)[-1]
        return {
            "text": f"DOC-{source.removeprefix('quote-').removesuffix('.txt')} quotation details",
            "source": source,
            "evidence": [{
                "source": source,
                "location": "page 1",
                "text": f"Quotation source {source}",
                "kind": "text",
            }],
            "truncated": False,
            "characters": 32,
        }


class _EmptyThenSuccessfulLLM:
    provider = "test"
    model = "test-model"

    def __init__(self):
        self.calls_by_document = {}

    def generate_json(self, prompt, system="", schema=None):
        document_id = prompt.split()[0].removeprefix("DOC-")
        attempt = self.calls_by_document.get(document_id, 0) + 1
        self.calls_by_document[document_id] = attempt

        # Simulate an extraction model returning an empty envelope for the
        # first pass on every file, then finding the quotation on recovery.
        if attempt == 1:
            return {"quotations": []}

        return {
            "quotations": [{
                "supplier": f"Supplier {document_id}",
                "quote_reference": f"Q-{document_id}",
                "total_cost": 1000 + int(document_id),
                "currency": "INR",
            }]
        }


def test_five_uploaded_documents_are_all_retried_and_included_in_comparison():
    agent = QuotationIntelligenceAgent.__new__(QuotationIntelligenceAgent)
    agent.llm = _EmptyThenSuccessfulLLM()
    agent.processor = _FiveDocumentProcessor()
    agent.web_search = None
    agent.state = AgentState()

    paths = [f"/uploads/quote-{index}.txt" for index in range(1, 6)]

    result = agent._process_documents(
        paths,
        query="Extract all supplier quotations",
        analyze=False,
    )

    assert len(result["documents"]) == 5
    assert result["metrics"]["document_count"] == 5
    assert result["metrics"]["quotation_count"] == 5
    assert {quote["supplier"] for quote in result["quotations"]} == {
        f"Supplier {index}" for index in range(1, 6)
    }
    assert {quote["source_document"] for quote in result["quotations"]} == {
        f"quote-{index}.txt" for index in range(1, 6)
    }
    assert all(document["extraction_attempts"] == 2 for document in result["documents"])
    assert all(document["extraction_status"] == "extracted" for document in result["documents"])
    assert all(len(document["quotations"]) == 1 for document in result["documents"])
