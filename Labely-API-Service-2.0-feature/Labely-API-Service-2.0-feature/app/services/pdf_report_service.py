# app/services/pdf_report_service.py - UPDATE this file

import logging
import os
from datetime import datetime
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

class PDFReportService:
    """PDF Report generation service."""

    def __init__(self):
        self.output_dir = settings.OUTPUT_FOLDER

    def create_report(self, results: List[Dict[str, Any]], process_id: str, orders_data: List[Dict[str, Any]] = None) -> str:
        """Create PDF report with order details - ONE PAGE PER ORDER with headers on each page"""
        report_path = os.path.join(self.output_dir, f"report_{process_id}.pdf")

        # Prepare data for the report
        report_data = self._prepare_report_data(results, orders_data)

        # Generate PDF with one page per order
        self._generate_pdf_with_pages(report_path, report_data, process_id)

        logger.info(f"Created PDF report at {report_path} with {len(report_data)} pages")
        return report_path

    def _prepare_report_data(self, results: List[Dict[str, Any]], orders_data: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Prepare and consolidate report data from results and orders.
        Remove duplicate entries where SKU, EAN, and quantity are identical.
        """
        from collections import OrderedDict

        report_data = []

        # Group results by order_id first
        orders_dict = {}
        for result in results:
            if result.get("status") != "success":
                continue

            order_id = result.get("order_id", "")
            if order_id not in orders_dict:
                orders_dict[order_id] = []
            orders_dict[order_id].append(result)

        # Process each order
        for order_id, order_results in orders_dict.items():
            # Find corresponding order data to get shipping address
            order_info = self._find_order_data(order_id, orders_data) if orders_data else {}

            # Format shipping address (once per order)
            shipping_address = self._format_shipping_address(order_info.get("shipping_address", {}))

            # Use OrderedDict to track unique lines based on SKU, EAN, and quantity
            unique_lines = OrderedDict()

            for result in order_results:
                # Create a unique key from SKU, EAN, and quantity
                sku = result.get("sku", "")
                ean = result.get("ean_code", "")
                quantity = result.get("quantity", 1)

                line_key = f"{sku}_{ean}_{quantity}"

                if line_key not in unique_lines:
                    # Create new line entry
                    unique_lines[line_key] = {
                        "order_id": order_id,
                        "sku": sku,
                        "ean_code": ean,
                        "description": result.get("description", ""),
                        "quantity": quantity,
                        "shipping_address": shipping_address,
                        "tracking_number": result.get("tracking_number", ""),
                        "campaign_number": result.get("campaign_number", ""),
                        "status": result.get("status", ""),
                        "error": result.get("error", "")
                    }

            # Add all unique lines to report data
            for line_data in unique_lines.values():
                report_data.append(line_data)

        # Debug: Log if we found and removed duplicates
        total_success = len([r for r in results if r.get("status") == "success"])
        if len(report_data) < total_success:
            logger.info(f"Removed {total_success - len(report_data)} duplicate rows from report (based on SKU+EAN+quantity)")

        return report_data

    def _find_order_data(self, order_id: str, orders_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Find order data by order ID."""
        for order in orders_data:
            if order.get("order_id") == order_id:
                return order
        return {}

    def _format_shipping_address(self, address: Dict[str, Any]) -> str:
        """Format shipping address into a readable string."""
        if not address or not any(address.values()):
            return "N/A"

        parts = []

        # Name
        name_parts = []
        if address.get("firstname"):
            name_parts.append(address.get("firstname"))
        if address.get("lastname"):
            name_parts.append(address.get("lastname"))
        if name_parts:
            parts.append(" ".join(name_parts))

        # Company (if exists)
        if address.get("company"):
            parts.append(address.get("company"))

        # City and zip (only these as per your PDF)
        if address.get("city"):
            parts.append(address.get("city"))
        if address.get("zip_code"):
            parts.append(address.get("zip_code"))

        # Country
        if address.get("country"):
            parts.append(address.get("country"))

        # Phone
        if address.get("phone"):
            parts.append(f"Tel: {address.get('phone')}")

        return ", ".join(parts) if parts else "N/A"

    def _generate_pdf_with_pages(self, filepath: str, data: List[Dict[str, Any]], process_id: str):
        """Generate PDF report with ONE PAGE PER ORDER - Each page has its own header and logo."""
        doc = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            rightMargin=15,
            leftMargin=15,
            topMargin=20,
            bottomMargin=20
        )

        styles = getSampleStyleSheet()

        # Custom styles - EXACTLY as in your original
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=14,
            alignment=TA_CENTER,
            spaceAfter=10
        )

        header_style = ParagraphStyle(
            'HeaderStyle',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Bold',
            alignment=TA_CENTER,
            textColor=colors.HexColor('#2c3e50'),
        )

        cell_style = ParagraphStyle(
            'CellStyle',
            parent=styles['Normal'],
            fontSize=7,
            alignment=TA_LEFT,
            wordWrap='CJK'
        )

        # ========================================
        # LOAD LOGO (same as original code)
        # ========================================
        logo = None

        try:
            # Construct path to local logo file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            logo_path = os.path.join(current_dir, '..', 'static', 'logo.png')
            logo_path = os.path.abspath(logo_path)

            logger.info(f"Looking for logo at: {logo_path}")

            if os.path.exists(logo_path):
                # Load the image
                logo = Image(logo_path, width=150, height=40)
                logger.info("  Logo loaded successfully from local file")
            else:
                logger.warning(f"Logo file not found at: {logo_path}")

                # Try alternative locations
                alt_paths = [
                    os.path.join(settings.BASE_DIR, 'static', 'logo.png') if hasattr(settings, 'BASE_DIR') else None,
                    os.path.join(os.getcwd(), 'static', 'logo.png'),
                    os.path.join(os.path.dirname(current_dir), 'static', 'logo.png')
                ]

                for alt_path in alt_paths:
                    if alt_path and os.path.exists(alt_path):
                        logo = Image(alt_path, width=110, height=40)
                        logger.info(f"  Logo loaded from alternative path: {alt_path}")
                        break

        except Exception as e:
            logger.error(f"Error loading logo: {str(e)}")
            logo = None

        # Create a text-based logo as fallback if image logo failed
        if not logo:
            try:
                text_logo_style = ParagraphStyle(
                    'TextLogo',
                    parent=styles['Normal'],
                    fontSize=16,
                    fontName='Helvetica-Bold',
                    textColor=colors.HexColor('#E30613'),  # Showroomprive red color
                    alignment=TA_LEFT
                )
                logo = Paragraph("SHOWROOM PRIVE", text_logo_style)
                logger.info("  Using text-based logo as fallback")
            except Exception as e:
                logger.warning(f"Could not create text logo: {e}")
                logo = None

        elements = []

        # Table headers - EXACTLY as in your original
        headers = [
            Paragraph("Order ID", header_style),
            Paragraph("SKU", header_style),
            Paragraph("EAN", header_style),
            Paragraph("Description", header_style),
            Paragraph("Qty", header_style),
            Paragraph("Shipping Address", header_style),
            Paragraph("Tracking #", header_style),
            Paragraph("Campaign #", header_style)
        ]

        # Group data by order_id to create one table per order
        orders_dict = {}
        for item in data:
            order_id = item["order_id"]
            if order_id not in orders_dict:
                orders_dict[order_id] = []
            orders_dict[order_id].append(item)

        # Create one page per order
        order_count = len(orders_dict)
        for order_idx, (order_id, order_items) in enumerate(orders_dict.items()):
            # ========================================
            # HEADER WITH LOGO AND TITLE - ADDED HERE
            # ========================================
            if logo:
                # Create table for header with logo on left, title on right
                header_table_data = [
                    [logo, Paragraph("Order Report", title_style)]
                ]

                header_table = Table(header_table_data, colWidths=[130, 400])
                header_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                    ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                    ('LEFTPADDING', (0, 0), (0, 0), 0),
                    ('RIGHTPADDING', (1, 0), (1, 0), 0),
                    ('TOPPADDING', (1, 0), (1, 0), 10),
                    ('BOTTOMPADDING', (1, 0), (1, 0), 10),
                ]))

                elements.append(header_table)
            else:
                # No logo at all, just title
                elements.append(Paragraph("Order Report", title_style))

            elements.append(Spacer(1, 0.1 * inch))

            # Add date for THIS PAGE
            date_text = f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Process Id: #{process_id}"
            elements.append(Paragraph(date_text, styles['Normal']))
            elements.append(Spacer(1, 0.2 * inch))

            # Create table for this order only
            table_data = [headers]

            for item in order_items:
                description = item["description"][:40] + "..." if len(item["description"]) > 40 else item["description"]
                shipping_address = item["shipping_address"][:90] + "..." if len(item["shipping_address"]) > 90 else item["shipping_address"]

                row = [
                    Paragraph(str(item["order_id"]), cell_style),
                    Paragraph(str(item["sku"]), cell_style),
                    Paragraph(str(item["ean_code"]), cell_style),
                    Paragraph(description, cell_style),
                    str(item["quantity"]),
                    Paragraph(shipping_address, cell_style),
                    Paragraph(str(item["tracking_number"]), cell_style),
                    Paragraph(str(item["campaign_number"]), cell_style)
                ]
                table_data.append(row)

            col_widths = [60, 50, 65, 90, 30, 140, 65, 65]
            table = Table(table_data, colWidths=col_widths, repeatRows=1)

            table_style = TableStyle([
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('TOPPADDING', (0, 0), (-1, 0), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#2c3e50')),
                ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
                ('ALIGN', (4, 1), (4, -1), 'CENTER'),
            ])

            table.setStyle(table_style)
            elements.append(table)

            # Add page break after each order EXCEPT the last one
            if order_idx < order_count - 1:
                elements.append(PageBreak())

        # Build PDF
        doc.build(elements)

pdf_report_service = PDFReportService()
