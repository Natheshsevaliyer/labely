import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd
from PyPDF2 import PdfMerger

from app.core.config import settings
from app.services.pdf_report_service import pdf_report_service

logger = logging.getLogger(__name__)

class FileService:
    """File handling service."""

    def __init__(self):
        self.output_dir = settings.OUTPUT_FOLDER
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Ensure required directories exist."""
        os.makedirs(self.output_dir, exist_ok=True)

    def create_report(self, results: List[Dict[str, Any]], process_id: str, orders_data: List[Dict[str, Any]] = None) -> str:
        """Create PDF report of processing results."""
        return pdf_report_service.create_report(results, process_id, orders_data)

    def create_tracking_file(self, results: List[Dict[str, Any]], process_id: str, orders_data: List[Dict[str, Any]] = None) -> str:
        """Create tracking CSV file for Mirakl import."""
        tracking_data = []

        for result in results:
            if result.get("tracking_number") and result.get("status") == "success":
                order_id = result.get("order_id", "")

                # Get order data
                order_info = {}
                if orders_data:
                    for order in orders_data:
                        if order.get("order_id") == order_id:
                            order_info = order
                            break

                tracking_data.append({
                    "order_id": order_id,
                    "tracking_number": result.get("tracking_number", ""),
                    "carrier_code": "SRP",
                    "carrier_name": "Colissimo",
                    "carrier_url": "https://www.laposte.fr/particulier/outils/suivre-vos-envois"
                })

        if tracking_data:
            df = pd.DataFrame(tracking_data)
            csv_path = os.path.join(self.output_dir, f"tracking_{process_id}.csv")
            df.to_csv(csv_path, index=False)

            # Also save Excel for backward compatibility
            excel_path = os.path.join(self.output_dir, f"tracking_{process_id}.xlsx")
            df.to_excel(excel_path, index=False)

            logger.info(f"Created tracking files for process {process_id}")
            return excel_path

        return ""

    def merge_pdfs(self, pdf_files: List[str], output_name: str = "merged_labels.pdf") -> str:
        """Merge multiple PDF files into one."""
        merger = PdfMerger()

        for pdf_file in pdf_files:
            if os.path.exists(pdf_file):
                merger.append(pdf_file)

        merged_path = os.path.join(self.output_dir, output_name)
        merger.write(merged_path)
        merger.close()

        logger.info(f"Merged {len(pdf_files)} PDFs to {merged_path}")
        return merged_path

    # In app/services/file_service.py - Add this method

    def merge_labels_only(self, label_files: List[str], process_id: str) -> str:
        """
        Merge all label PDFs into a single PDF file (labels only, no reports).
        Returns the path to the merged labels PDF.
        """
        from PyPDF2 import PdfMerger

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"labels_only_{process_id}_{timestamp}.pdf"
        output_path = os.path.join(self.output_dir, output_filename)

        if not label_files:
            logger.warning(f"No label files to merge for process {process_id}")
            return ""

        merger = PdfMerger()
        valid_files = 0

        for i, label_file in enumerate(label_files):
            if os.path.exists(label_file):
                merger.append(label_file)
                valid_files += 1
                logger.debug(f"Added label {i+1}: {label_file}")
            else:
                logger.warning(f"Label file not found: {label_file}")

        if valid_files > 0:
            merger.write(output_path)
            merger.close()
            logger.info(f"  Created labels-only PDF with {valid_files} labels: {output_path}")
            return output_path
        else:
            merger.close()
            logger.error(f"No valid label files found for process {process_id}")
            return ""

    # def create_archive(self, process_id: str, include_pdfs: bool = True) -> str:
    #     """Create ZIP archive of generated files for a specific process."""
    #     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    #     archive_name = f"labels_{process_id}_{timestamp}.zip"
    #     archive_path = os.path.join(self.output_dir, archive_name)

    #     with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
    #         # Add PDF report
    #         report_path = os.path.join(self.output_dir, f"report_{process_id}.pdf")
    #         if os.path.exists(report_path):
    #             zipf.write(report_path, os.path.basename(report_path))

    #         # Add tracking file
    #         tracking_path = os.path.join(self.output_dir, f"tracking_{process_id}.csv")
    #         if os.path.exists(tracking_path):
    #             zipf.write(tracking_path, os.path.basename(tracking_path))

    #         # Also include Excel tracking if exists
    #         tracking_excel = os.path.join(self.output_dir, f"tracking_{process_id}.xlsx")
    #         if os.path.exists(tracking_excel):
    #             zipf.write(tracking_excel, os.path.basename(tracking_excel))

    #         # Add merged labels PDF
    #         labels_path = os.path.join(self.output_dir, f"labels_{process_id}.pdf")
    #         if os.path.exists(labels_path):
    #             zipf.write(labels_path, os.path.basename(labels_path))

    #         # Add individual label PDFs
    #         for filename in os.listdir(self.output_dir):
    #             if filename.startswith(f"{process_id}_") and filename.endswith('.pdf'):
    #                 file_path = os.path.join(self.output_dir, filename)
    #                 zipf.write(file_path, filename)

    #     logger.info(f"Created archive at {archive_path}")
    #     return archive_path

    def cleanup_old_files(self, minutes_old: int = 30):
        """Clean up files older than specified minutes."""
        cutoff_time = time.time() - (minutes_old * 60)

        for root, dirs, files in os.walk(self.output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                if os.path.isfile(file_path) and os.path.getmtime(file_path) < cutoff_time:
                    try:
                        os.remove(file_path)
                        logger.debug(f"Removed old file: {file_path}")
                    except Exception as e:
                        logger.error(f"Failed to remove {file_path}: {e}")

        logger.info("Cleaned up old files")

file_service = FileService()
