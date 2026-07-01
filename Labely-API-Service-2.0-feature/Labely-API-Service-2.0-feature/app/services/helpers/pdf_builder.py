"""Shared PDF construction utilities (logo loading, interleaved merge)."""
import logging
import os
from typing import List

logger = logging.getLogger(__name__)

_STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "static"))


def load_logo(width: int = 150, height: int = 40):
    """Return a ReportLab Image for the company logo, or None if unavailable."""
    try:
        from reportlab.platypus import Image  # type: ignore

        logo_path = os.path.join(_STATIC_DIR, "logo.png")
        if os.path.exists(logo_path):
            return Image(logo_path, width=width, height=height)
        logger.debug("Logo not found at %s", logo_path)
    except Exception as exc:
        logger.warning("Could not load logo: %s", exc)
    return None


def build_interleaved_pdf(
    output_path: str,
    label_paths: List[str],
    report_path: str,
) -> bool:
    """
    Merge label PDFs and report pages into a single interleaved PDF.

    Layout: for each index i → all pages of label_paths[i] then report_path[page i].

    Returns:
        True on success, False on failure.
    """
    try:
        from PyPDF2 import PdfReader, PdfWriter  # type: ignore

        if not os.path.exists(report_path):
            logger.error("Report PDF not found at %s", report_path)
            return False

        report_reader = PdfReader(report_path)
        report_page_count = len(report_reader.pages)

        writer = PdfWriter()

        for i, label_path in enumerate(label_paths):
            if os.path.exists(label_path):
                for page in PdfReader(label_path).pages:
                    writer.add_page(page)
            else:
                logger.warning("Label PDF missing: %s", label_path)

            if i < report_page_count:
                writer.add_page(report_reader.pages[i])

        with open(output_path, "wb") as fh:
            writer.write(fh)

        logger.info("Interleaved PDF written to %s (%d label(s))", output_path, len(label_paths))
        return True

    except Exception as exc:
        logger.error("build_interleaved_pdf failed: %s", exc, exc_info=True)
        return False
