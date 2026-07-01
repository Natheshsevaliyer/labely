import base64
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from PyPDF2 import PdfMerger
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.config import settings

logger = logging.getLogger(__name__)

class PDFService:
    """PDF handling service for labels and reports."""

    def __init__(self):
        self.output_folder = Path(settings.OUTPUT_FOLDER)
        self.output_folder.mkdir(parents=True, exist_ok=True)

        # Create subfolders
        self.labels_folder = self.output_folder / "labels"
        self.reports_folder = self.output_folder / "reports"
        self.merged_folder = self.output_folder / "merged"

        self.labels_folder.mkdir(exist_ok=True)
        self.reports_folder.mkdir(exist_ok=True)
        self.merged_folder.mkdir(exist_ok=True)

    async def save_label_pdf(self, order_id: str, label_data: Any, tracking_number: str) -> str:
        """Save label PDF from SRP response."""
        try:
            filename = f"label_{order_id}_{tracking_number}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
            filepath = self.labels_folder / filename

            if isinstance(label_data, str):
                if label_data.startswith('data:application/pdf;base64,'):
                    label_data = label_data.split(',')[1]
                pdf_bytes = base64.b64decode(label_data)
            elif isinstance(label_data, bytes):
                pdf_bytes = label_data
            else:
                raise ValueError(f"Unsupported label data type: {type(label_data)}")

            with open(filepath, 'wb') as f:
                f.write(pdf_bytes)

            logger.info(f"Saved label PDF: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"Failed to save label PDF for order {order_id}: {str(e)}")
            raise

    async def generate_order_report(self, order: Any, tracking_number: str, label_data: Dict) -> str:
        """Generate a report PDF for an order."""
        try:
            filename = f"report_{order.order_id}_{tracking_number}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
            filepath = self.reports_folder / filename

            doc = SimpleDocTemplate(
                str(filepath),
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=18,
            )

            elements = []
            styles = getSampleStyleSheet()
            title_style = styles['Heading1']
            heading_style = styles['Heading2']
            normal_style = styles['Normal']

            elements.append(Paragraph("Order Label Generation Report", title_style))
            elements.append(Spacer(1, 0.25 * inch))

            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            elements.append(Paragraph(f"Generated: {timestamp}", normal_style))
            elements.append(Spacer(1, 0.25 * inch))

            # Order Information
            elements.append(Paragraph("Order Information", heading_style))
            elements.append(Spacer(1, 0.1 * inch))

            order_data = [
                ["Order ID:", order.order_id],
                ["SRP/Carrier:", getattr(order, 'carrier_manager', 'N/A')],
                ["Order Date:", str(getattr(order, 'order_date', 'N/A'))],
                ["Order State:", getattr(order, 'order_state', 'N/A')],
            ]

            order_table = Table(order_data, colWidths=[2 * inch, 4 * inch])
            order_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ]))

            elements.append(order_table)
            elements.append(Spacer(1, 0.25 * inch))

            # Label Information
            elements.append(Paragraph("Label Information", heading_style))
            elements.append(Spacer(1, 0.1 * inch))

            label_info = [
                ["Tracking Number:", tracking_number],
                ["Label Generated:", "Yes"],
                ["Generation Status:", "Success"],
            ]

            label_table = Table(label_info, colWidths=[2 * inch, 4 * inch])
            label_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ]))

            elements.append(label_table)
            elements.append(Spacer(1, 0.25 * inch))

            doc.build(elements)

            logger.info(f"Generated report PDF: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"Failed to generate report for order {order.order_id}: {str(e)}")
            raise

    async def merge_pdfs(self, pdf_files: List[str], output_filename: str) -> str:
        """Merge multiple PDF files into one."""
        try:
            output_path = self.merged_folder / output_filename

            merger = PdfMerger()

            for pdf_file in pdf_files:
                if os.path.exists(pdf_file):
                    merger.append(pdf_file)
                    logger.info(f"Appended {pdf_file} to merged PDF")
                else:
                    logger.warning(f"PDF file not found: {pdf_file}")

            merger.write(str(output_path))
            merger.close()

            logger.info(f"Created merged PDF: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Failed to merge PDFs: {str(e)}")
            raise

pdf_service = PDFService()
