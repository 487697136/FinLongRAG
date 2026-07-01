from finlongrag.core.schema import Document
from finlongrag.ingestion import parser
from finlongrag.ingestion.parser import markdown_to_pages


def test_markdown_to_pages_splits_by_opendataloader_separator():
    document = Document(doc_id="demo", domain="reports", title="Demo", path="demo.pdf")
    markdown = (
        "# Page 1 title\n\nBody on page 1.\n\n"
        "---PAGE-2---\n\n"
        "## Page 2\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
    )

    pages = markdown_to_pages(markdown, document, document.path_obj)

    assert len(pages) == 2
    assert pages[0].page == 1
    assert "Page 1 title" in pages[0].text
    assert pages[1].page == 2
    assert "| 1 | 2 |" in pages[1].text
    assert pages[0].metadata["parser"] == "opendataloader-pdf"


def test_convert_pdf_filters_unsupported_kwargs(monkeypatch, tmp_path):
    seen = {}

    def fake_convert(input_path, output_dir=None, format=None, quiet=False):
        seen.update(
            {
                "input_path": input_path,
                "output_dir": output_dir,
                "format": format,
                "quiet": quiet,
            }
        )

    monkeypatch.setattr(parser.opendataloader_pdf, "convert", fake_convert)

    parser._convert_pdf(
        output_dir=tmp_path,
        convert_kwargs={
            "input_path": "demo.pdf",
            "format": "markdown",
            "quiet": True,
            "markdown_with_html": True,
            "image_output": "off",
        },
    )

    assert seen == {
        "input_path": "demo.pdf",
        "output_dir": str(tmp_path),
        "format": "markdown",
        "quiet": True,
    }


def test_parse_pdf_supports_markdown_returned_directly(monkeypatch, tmp_path):
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
    document = Document(doc_id="demo", domain="reports", title="Demo", path=str(pdf_path))

    def fake_convert(*args, **kwargs):
        _ = args, kwargs
        return "# p1\n\nhello\n\n---PAGE-2---\n\nworld"

    monkeypatch.setattr(parser, "_opendataloader_preflight_error", lambda: None)
    monkeypatch.setattr(parser.opendataloader_pdf, "convert", fake_convert)

    pages = parser._parse_pdf(pdf_path, document, settings=None)
    assert len(pages) == 2
    assert pages[0].page == 1
    assert "hello" in pages[0].text
    assert pages[1].page == 2


def test_parse_pdf_falls_back_to_text_output(monkeypatch, tmp_path):
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
    document = Document(doc_id="demo", domain="reports", title="Demo", path=str(pdf_path))

    def fake_convert(input_path, output_dir=None, format=None, quiet=False, text_page_separator=None):
        _ = input_path, quiet, text_page_separator
        fmt = format
        if fmt == "text" and output_dir:
            from pathlib import Path
            (Path(output_dir) / "demo.txt").write_text("p1\n\n---PAGE-2---\n\np2", encoding="utf-8")
        return None

    monkeypatch.setattr(parser, "_opendataloader_preflight_error", lambda: None)
    monkeypatch.setattr(parser.opendataloader_pdf, "convert", fake_convert)

    pages = parser._parse_pdf(pdf_path, document, settings=None)
    assert len(pages) == 2
    assert pages[0].metadata["parser"] == "opendataloader-pdf:text"
    assert "p2" in pages[1].text


def test_parse_pdf_falls_back_to_pymupdf(monkeypatch, tmp_path):
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
    document = Document(doc_id="demo", domain="reports", title="Demo", path=str(pdf_path))

    class FakePage:
        def __init__(self, text):
            self._text = text

        def get_text(self, *_args, **_kwargs):
            return self._text

    class FakePdf:
        def __iter__(self):
            return iter([FakePage(""), FakePage("page2 text")])

        def close(self):
            pass

    def fake_convert(input_path, output_dir=None, format=None, quiet=False, text_page_separator=None):
        _ = input_path, output_dir, format, quiet, text_page_separator
        return None

    class FakeFitz:
        @staticmethod
        def open(_path):
            return FakePdf()

    monkeypatch.setattr(parser, "_opendataloader_preflight_error", lambda: None)
    monkeypatch.setattr(parser.opendataloader_pdf, "convert", fake_convert)
    monkeypatch.setattr(parser, "_has_tesseract", lambda: False)
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "fitz":
            return FakeFitz
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    pages = parser._parse_pdf(pdf_path, document, settings=None)
    assert len(pages) == 1
    assert pages[0].metadata["parser"] == "pymupdf"
    assert "page2 text" in pages[0].text


def test_parse_pdf_skips_opendataloader_when_java_is_too_old(monkeypatch, tmp_path):
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
    document = Document(doc_id="demo", domain="reports", title="Demo", path=str(pdf_path))

    def fail_convert(*_args, **_kwargs):
        raise AssertionError("opendataloader should be skipped when Java is too old")

    class FakePage:
        def get_text(self, *_args, **_kwargs):
            return "fallback text"

    class FakePdf:
        def __iter__(self):
            return iter([FakePage()])

        def close(self):
            pass

    class FakeFitz:
        @staticmethod
        def open(_path):
            return FakePdf()

    monkeypatch.setattr(parser, "_opendataloader_preflight_error", lambda: "Java 8 is too old")
    monkeypatch.setattr(parser.opendataloader_pdf, "convert", fail_convert)
    monkeypatch.setattr(parser, "_has_tesseract", lambda: False)

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "fitz":
            return FakeFitz
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    pages = parser._parse_pdf(pdf_path, document, settings=None)
    assert len(pages) == 1
    assert pages[0].metadata["parser"] == "pymupdf"
    assert "fallback text" in pages[0].text
