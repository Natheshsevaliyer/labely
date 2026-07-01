import os
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.api import deps
from app.core.config import settings
from app.core.exceptions import NotFoundException

router = APIRouter()

@router.get("/labels/{process_id}")
async def download_labels_pdf(
    process_id: str,
    current_user = Depends(deps.get_current_user)
):
    """Download merged labels PDF"""
    output_dir = settings.OUTPUT_FOLDER

    # Find the PDF file
    for filename in os.listdir(output_dir):
        if filename.startswith(f"labels_report_{process_id}_") and filename.endswith('.pdf'):
            file_path = os.path.join(output_dir, filename)
            if os.path.exists(file_path):
                return FileResponse(
                    path=file_path,
                    filename=filename,
                    media_type='application/pdf'
                )

    # Try old pattern
    old_path = os.path.join(output_dir, f"labels_{process_id}.pdf")
    if os.path.exists(old_path):
        return FileResponse(
            path=old_path,
            filename=f"labels_{process_id}.pdf",
            media_type='application/pdf'
        )

    raise NotFoundException(f"Labels PDF not found for process {process_id}")

# In app/api/v1/endpoints/download.py - Add this new endpoint

@router.get("/labels-only/{process_id}")
async def download_labels_only(
    process_id: str,
    filename: Optional[str] = None,
    current_user = Depends(deps.get_current_user)
):
    """Download PDF containing ONLY merged labels (no reports)"""
    output_dir = settings.OUTPUT_FOLDER

    if filename and os.path.exists(os.path.join(output_dir, filename)):
        file_path = os.path.join(output_dir, filename)
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type='application/pdf'
        )

    # Find the latest labels-only file for this process
    pattern = f"labels_only_{process_id}_"
    for filename in sorted(os.listdir(output_dir), reverse=True):
        if filename.startswith(pattern) and filename.endswith('.pdf'):
            file_path = os.path.join(output_dir, filename)
            return FileResponse(
                path=file_path,
                filename=filename,
                media_type='application/pdf'
            )

    raise NotFoundException(f"Labels-only PDF not found for process {process_id}")

@router.get("/report/{process_id}")
async def download_report(
    process_id: str,
    current_user = Depends(deps.get_current_user)
):
    """Download PDF report"""
    output_dir = settings.OUTPUT_FOLDER
    filename = f"report_{process_id}.pdf"
    file_path = os.path.join(output_dir, filename)

    if os.path.exists(file_path):
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type='application/pdf'
        )

    raise NotFoundException("Report not found")

@router.get("/tracking/{process_id}")
async def download_tracking(
    process_id: str,
    current_user = Depends(deps.get_current_user)
):
    """Download tracking CSV file"""
    output_dir = settings.OUTPUT_FOLDER

    # Try CSV first
    csv_path = os.path.join(output_dir, f"tracking_{process_id}.csv")
    if os.path.exists(csv_path):
        return FileResponse(
            path=csv_path,
            filename=f"tracking_{process_id}.csv",
            media_type='text/csv'
        )

    # Try Excel
    excel_path = os.path.join(output_dir, f"tracking_{process_id}.xlsx")
    if os.path.exists(excel_path):
        return FileResponse(
            path=excel_path,
            filename=f"tracking_{process_id}.xlsx",
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    raise NotFoundException("Tracking file not found")

@router.get("/archive/{process_id}")
async def download_archive(
    process_id: str,
    current_user = Depends(deps.get_current_user)
):
    """Download ZIP archive of generated files"""
    output_dir = settings.OUTPUT_FOLDER

    for filename in os.listdir(output_dir):
        if filename.startswith(f"labels_{process_id}_") and filename.endswith('.zip'):
            file_path = os.path.join(output_dir, filename)
            return FileResponse(
                file_path,
                filename=filename,
                media_type='application/zip'
            )

    raise NotFoundException("Archive not found")
__all__ = ["router"]
