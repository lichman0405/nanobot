"""Paper download and PDF parsing tool."""

import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from nanobot.agent.tools.base import Tool

# Maximum PDF file size to download (50 MB)
MAX_PDF_SIZE = 50 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; nanobot-research/1.0)"


class PaperDownloadTool(Tool):
    """Download a paper PDF and extract text content."""

    name = "paper_download"
    description = (
        "Download a paper PDF from URL and extract text. Saves PDF to "
        "workspace/mof_data/papers/. Returns extracted text."
    )
    # NOTE: Flat schema for DeepSeek compat. When upgrading to GPT-5.2/Sonnet 4.5, consider richer nested schemas.
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "PDF URL (from scholar_search or arxiv_search results)",
            },
            "filename": {
                "type": "string",
                "description": "Optional filename (without .pdf extension). Auto-generated if omitted.",
            },
        },
        "required": ["url"],
    }

    def __init__(self, workspace: Path | None = None):
        self.workspace = workspace or Path.cwd()
        self.papers_dir = self.workspace / "mof_data" / "papers"

    async def execute(self, url: str, filename: str | None = None, **kwargs: Any) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return "Error: Only http/https URLs supported"

        self.papers_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            path_parts = parsed.path.rstrip("/").split("/")
            name_part = path_parts[-1] if path_parts else url_hash
            name_part = re.sub(r"\.pdf$", "", name_part, flags=re.I)
            name_part = re.sub(r"[^\w\-.]", "_", name_part)
            filename = f"{name_part}_{url_hash}"
        filename = self._sanitize_filename(filename)

        pdf_path = self.papers_dir / f"{filename}.pdf"
        tmp_pdf_path = self.papers_dir / f"{filename}.pdf.part"
        txt_path = self.papers_dir / f"{filename}.txt"

        if txt_path.exists():
            text = txt_path.read_text(encoding="utf-8", errors="replace")
            return (
                f"Already downloaded. File: {pdf_path}\n\n"
                f"Extracted text ({len(text)} chars):\n{text[:8000]}"
            )

        downloaded_size = 0
        try:
            async with httpx.AsyncClient(follow_redirects=True, max_redirects=5) as client:
                async with client.stream(
                    "GET",
                    url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=30.0,
                ) as response:
                    response.raise_for_status()

                    content_type = response.headers.get("content-type", "").lower()
                    if "pdf" not in content_type and not url.lower().endswith(".pdf"):
                        if "html" in content_type:
                            return (
                                "Error: URL returned HTML instead of PDF. "
                                f"This is likely a paywall. Content-Type: {content_type}"
                            )

                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            expected_size = int(content_length)
                            if expected_size > MAX_PDF_SIZE:
                                return (
                                    f"Error: PDF too large ({expected_size} bytes, "
                                    f"max {MAX_PDF_SIZE})"
                                )
                        except ValueError:
                            pass

                    if tmp_pdf_path.exists():
                        tmp_pdf_path.unlink()

                    with tmp_pdf_path.open("wb") as file_obj:
                        async for chunk in response.aiter_bytes(chunk_size=1024 * 64):
                            if not chunk:
                                continue
                            downloaded_size += len(chunk)
                            if downloaded_size > MAX_PDF_SIZE:
                                file_obj.close()
                                tmp_pdf_path.unlink(missing_ok=True)
                                return (
                                    f"Error: PDF too large ({downloaded_size} bytes, "
                                    f"max {MAX_PDF_SIZE})"
                                )
                            file_obj.write(chunk)

            tmp_pdf_path.replace(pdf_path)
        except httpx.HTTPStatusError as e:
            tmp_pdf_path.unlink(missing_ok=True)
            return f"Error: HTTP {e.response.status_code} downloading PDF"
        except Exception as e:
            tmp_pdf_path.unlink(missing_ok=True)
            return f"Error downloading PDF: {e}"

        text = self._extract_text(pdf_path)
        if text:
            txt_path.write_text(text, encoding="utf-8")

        summary = text[:8000] if text else "(no text extracted)"
        return (
            f"Downloaded: {pdf_path} ({downloaded_size} bytes)\n\n"
            f"Extracted text ({len(text)} chars):\n{summary}"
        )

    def _extract_text(self, pdf_path: Path) -> str:
        """Extract text from PDF using available tools."""
        try:
            import fitz  # type: ignore

            doc = fitz.open(str(pdf_path))
            pages = []
            for page in doc:
                pages.append(page.get_text())
            doc.close()
            return "\n\n--- Page Break ---\n\n".join(pages)
        except ImportError:
            pass

        import subprocess

        try:
            result = subprocess.run(
                ["pdftotext", "-layout", str(pdf_path), "-"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return (
            "(PDF text extraction failed. Install PyMuPDF: pip install pymupdf, "
            "or install poppler-utils: apt install poppler-utils)"
        )

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        cleaned = re.sub(r"[^\w\-.]", "_", name.strip())
        cleaned = cleaned.strip("._")
        return cleaned or "paper"
