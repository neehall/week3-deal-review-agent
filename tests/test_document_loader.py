"""Unit tests for document_loader.load_document()'s error paths.

No API key required -- these never touch the LLM, only file parsing.
"""

import pytest

from app.tools.document_loader import DocumentLoadError, load_document


def test_loads_txt_file(tmp_path):
    f = tmp_path / "deal.txt"
    f.write_text("Some deal text.")
    assert load_document(str(f)) == "Some deal text."


def test_missing_file_raises():
    with pytest.raises(DocumentLoadError):
        load_document("/nonexistent/path.txt")


def test_unsupported_type_raises(tmp_path):
    f = tmp_path / "deal.xyz"
    f.write_text("content")
    with pytest.raises(DocumentLoadError):
        load_document(str(f))


def test_empty_file_raises(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("   ")
    with pytest.raises(DocumentLoadError):
        load_document(str(f))
