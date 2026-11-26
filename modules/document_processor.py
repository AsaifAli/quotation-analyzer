"""Safe multi-format ingestion with page/sheet evidence and optional OCR fallback."""
import os
import zipfile
from dataclasses import dataclass, asdict
from typing import Any, Dict, List
from pypdf import PdfReader
from docx import Document
import pandas as pd
import config


@dataclass
class DocumentEvidence:
    source: str
    location: str
    text: str
    kind: str = "text"

    def to_dict(self):
        return asdict(self)


class DocumentProcessor:
    def __init__(self):
        self.supported_formats = set(config.SUPPORTED_FORMATS)

    def _validate_file_signature(self, file_path: str, extension: str) -> None:
        """Check server-observed file bytes instead of trusting the filename."""
        with open(file_path, "rb") as source:
            prefix = source.read(1024)

        if extension == ".pdf":
            if b"%PDF-" not in prefix:
                raise ValueError("File contents do not match PDF format.")
            return

        if extension == ".txt":
            # Text uploads may contain arbitrary UTF-8 text, but NUL bytes are
            # a strong signal that a binary file was renamed to .txt.
            if b"\x00" in prefix:
                raise ValueError("File contents do not match TXT format.")
            return

        expected_member = (
            "word/document.xml" if extension == ".docx" else "xl/workbook.xml"
        )
        try:
            with zipfile.ZipFile(file_path) as archive:
                members = archive.infolist()
                names = {member.filename for member in members}
                if (
                    "[Content_Types].xml" not in names
                    or expected_member not in names
                ):
                    raise ValueError(
                        f"File contents do not match {extension[1:].upper()} format."
                    )

                # Prevent small compressed uploads from expanding into
                # unbounded XML payloads during Office document parsing.
                if len(members) > 10_000:
                    raise ValueError("Office document contains too many archive entries.")
                if sum(member.file_size for member in members) > 512 * 1024 * 1024:
                    raise ValueError("Office document expands beyond the safe size limit.")
        except zipfile.BadZipFile as exc:
            raise ValueError(
                f"File contents do not match {extension[1:].upper()} format."
            ) from exc

    def validate_file(self, file_path):
        if not os.path.isfile(file_path):
            raise ValueError("Document does not exist.")
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self.supported_formats:
            raise ValueError(
                f"Unsupported format: {ext}. Supported: {sorted(self.supported_formats)}"
            )
        if os.path.getsize(file_path) > config.MAX_FILE_SIZE_MB * 1024 * 1024:
            raise ValueError(f"File exceeds {config.MAX_FILE_SIZE_MB} MB limit.")
        self._validate_file_signature(file_path, ext)

    def extract(self, file_path):
        self.validate_file(file_path)
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            text, evidence = self._pdf(file_path)
        elif ext == ".docx":
            text, evidence = self._docx(file_path)
        elif ext == ".txt":
            text, evidence = self._txt(file_path)
        else:
            text, evidence = self._xlsx(file_path)
        truncated = len(text) > config.MAX_DOCUMENT_CHARS
        return {
            "text": text[:config.MAX_DOCUMENT_CHARS],
            "evidence": evidence,
            "truncated": truncated,
            "source": os.path.basename(file_path),
            "characters": min(len(text), config.MAX_DOCUMENT_CHARS),
        }

    def extract_text(self, file_path):
        return self.extract(file_path)["text"]

    def _pdf(self, path):
        pages, evidence = [], []
        with open(path, "rb") as f:
            reader = PdfReader(f)
            if len(reader.pages) > config.MAX_DOCUMENT_PAGES:
                raise ValueError(
                    f"PDF exceeds the {config.MAX_DOCUMENT_PAGES}-page processing limit."
                )
            for i, page in enumerate(reader.pages, 1):
                page_text = (page.extract_text() or "").strip()
                kind = "text"
                if not page_text and config.OCR_ENABLED:
                    page_text = self._ocr_page(path, i) or ""
                    kind = "ocr" if page_text else "text"
                pages.append(f"[Page {i}]\n{page_text}")
                evidence.append(
                    DocumentEvidence(
                        os.path.basename(path),
                        f"page {i}",
                        page_text[:4000],
                        kind,
                    ).to_dict()
                )
        if not pages:
            raise ValueError("PDF contains no readable pages.")
        return "\n\n".join(pages), evidence

    def _ocr_page(self, path, page_number):
        try:
            import pymupdf as fitz
            import pytesseract
            from PIL import Image

            doc = fitz.open(path)
            page = doc.load_page(page_number - 1)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            return pytesseract.image_to_string(image).strip()
        except Exception:
            return ""

    def _docx(self, path):
        doc = Document(path)
        blocks = []
        evidence = []
        for i, paragraph in enumerate(doc.paragraphs, 1):
            if paragraph.text.strip():
                blocks.append(paragraph.text.strip())
                evidence.append(
                    DocumentEvidence(
                        os.path.basename(path),
                        f"paragraph {i}",
                        paragraph.text.strip()[:4000],
                    ).to_dict()
                )
        for table_index, table in enumerate(doc.tables, 1):
            rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
            text = "\n".join(rows)
            if text:
                blocks.append(f"[Table {table_index}]\n{text}")
                evidence.append(
                    DocumentEvidence(
                        os.path.basename(path),
                        f"table {table_index}",
                        text[:4000],
                        "table",
                    ).to_dict()
                )
        return "\n".join(blocks), evidence

    def _txt(self, path):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        return text, [
            DocumentEvidence(os.path.basename(path), "text file", text[:4000]).to_dict()
        ]

    def _xlsx(self, path):
        sheets = pd.read_excel(path, sheet_name=None)
        blocks = []
        evidence = []
        for name, frame in sheets.items():
            text = frame.fillna("").to_string(index=False)
            blocks.append(f"[Sheet: {name}]\n{text}")
            evidence.append(
                DocumentEvidence(
                    os.path.basename(path),
                    f"sheet {name}",
                    text[:4000],
                    "table",
                ).to_dict()
            )
        return "\n\n".join(blocks), evidence
