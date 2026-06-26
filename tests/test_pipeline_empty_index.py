from pathlib import Path

from finlongrag.service.pipeline import _load_bm25_or_empty, _load_document_index_or_empty


def test_pipeline_loaders_accept_missing_indexes(tmp_path: Path) -> None:
    bm25 = _load_bm25_or_empty(tmp_path / "missing_bm25.pkl", tokenizer_mode="mixed")
    doc_index = _load_document_index_or_empty(tmp_path / "missing_document.pkl", tokenizer_mode="mixed")

    assert bm25.search("任意问题") == []
    assert doc_index.search_doc_ids("任意问题") == []
