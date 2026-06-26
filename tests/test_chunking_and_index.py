from finlongrag.core.schema import Document, PageText
from finlongrag.index.bm25 import BM25FIndex
from finlongrag.ingestion.chunker import chunk_document, extract_numbers


def test_chunker_preserves_financial_numbers_and_bm25f_retrieves():
    document = Document(doc_id="demo_report", domain="financial_reports", title="Demo 2025", path="demo.pdf")
    pages = [
        PageText(
            doc_id="demo_report",
            domain="financial_reports",
            page=1,
            text="一、主要财务指标\n营业收入 2025年 120亿元 2024年 100亿元\n归属于上市公司股东的净利润为20亿元。",
        )
    ]

    chunks = chunk_document(document, pages)

    assert chunks
    assert any("120亿元" in number.replace(" ", "") for chunk in chunks for number in chunk.numbers)
    assert "120亿元" in "".join(extract_numbers(pages[0].text)).replace(" ", "")

    index = BM25FIndex.build(chunks)
    hits = index.search("营业收入 2025年 120亿元", top_k=3)

    assert hits
    assert hits[0].doc_id == "demo_report"
    assert "营业收入" in hits[0].evidence_text

