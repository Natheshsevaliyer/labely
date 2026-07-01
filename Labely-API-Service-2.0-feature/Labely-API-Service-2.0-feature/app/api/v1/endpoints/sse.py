# app/api/v1/endpoints/sse.py - COMPLETE REPLACEMENT

# app/api/v1/endpoints/sse.py
import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api import deps
from app.core.exceptions import NotFoundException
from app.services.order_service import OrderService
from app.services.sse_manager import sse_manager

router = APIRouter()

@router.get("/process/{process_id}/stream")
async def stream_process_status(
    request: Request,
    process_id: int,
    current_user = Depends(deps.get_current_user),
    db = Depends(deps.get_db)
):
    """
    Stream real-time status updates for a process using Server-Sent Events.
    Includes download URLs and failed orders when process completes.
    """
    # Verify process exists
    service = OrderService(db)
    try:
        initial_status = await service.get_process_status(process_id, current_user.id)
    except NotFoundException:
        raise NotFoundException(f"Process {process_id} not found")

    async def event_generator():
        queue = await sse_manager.connect(str(process_id))

        try:
            # Send connected event
            yield f"event: connected\ndata: {json.dumps({'process_id': process_id})}\n\n"

            # Send initial status (already includes URLs if completed)
            yield f"event: status_update\ndata: {json.dumps(initial_status, default=str)}\n\n"

            # Check if already completed
            if initial_status['status'] in ['Completed', 'Failed', 'Partial']:
                # Send complete event with all data including failed_orders
                complete_data = {
                    'event': 'complete',
                    'message': 'Process already completed',
                    'download_url': initial_status.get('download_url'),
                    'labels_only_url': initial_status.get('labels_only_url'),
                    'report_url': initial_status.get('report_url'),
                    'status': initial_status['status'],
                    'successful': initial_status.get('successful', 0),
                    'failed': initial_status.get('failed', 0),
                    'total': initial_status.get('total', 0),
                    'failed_orders': initial_status.get('failed_orders', []),
                    'failed_count': initial_status.get('failed_count', 0)
                }
                yield f"event: complete\ndata: {json.dumps(complete_data, default=str)}\n\n"
                return

            while True:
                try:
                    if await request.is_disconnected():
                        break

                    message = await asyncio.wait_for(queue.get(), timeout=2)

                    # Parse the message to check status
                    if message.startswith('event: status_update'):
                        # Extract data
                        data_str = message.split('data: ')[1].strip()
                        status_data = json.loads(data_str)

                        # If final status, forward the original message and then send complete event
                        if status_data.get('status') in ['Completed', 'Failed', 'Partial']:
                            # Forward the original status_update message (which may contain failed_orders if we add it there)
                            yield message

                            # Send complete event - try to get failed_orders from status_data or from sse_manager
                            # First check if status_data already has failed_orders
                            failed_orders = status_data.get('failed_orders', [])
                            failed_count = status_data.get('failed_count', len(failed_orders))

                            # If not, check if sse_manager has completed status
                            if not failed_orders and sse_manager.is_completed(str(process_id)):
                                completed_status = sse_manager.get_completed_status(str(process_id))
                                if completed_status:
                                    failed_orders = completed_status.get('failed_orders', [])
                                    failed_count = completed_status.get('failed_count', len(failed_orders))

                            complete_data = {
                                'event': 'complete',
                                'message': 'Process completed',
                                'download_url': status_data.get('download_url'),
                                'labels_only_url': status_data.get('labels_only_url'),
                                'report_url': status_data.get('report_url'),
                                'status': status_data.get('status'),
                                'successful': status_data.get('successful', 0),
                                'failed': status_data.get('failed', 0),
                                'total': status_data.get('total', 0),
                                'failed_orders': failed_orders,
                                'failed_count': failed_count
                            }
                            yield f"event: complete\ndata: {json.dumps(complete_data, default=str)}\n\n"
                            break

                    yield message

                except asyncio.TimeoutError:
                    # Only send heartbeat if process not completed
                    # Check current status from service to be sure
                    current_status = await service.get_process_status(process_id, current_user.id)
                    if current_status['status'] in ['Completed', 'Failed', 'Partial']:
                        # Send final status with URLs and failed orders
                        status_update = {
                            "process_id": process_id,
                            "status": current_status['status'],
                            "total": current_status.get('total', 0),
                            "successful": current_status.get('successful', 0),
                            "failed": current_status.get('failed', 0),
                            "download_url": current_status.get('download_url'),
                            "labels_only_url": current_status.get('labels_only_url'),
                            "report_url": current_status.get('report_url'),
                            "failed_orders": current_status.get('failed_orders', []),
                            "failed_count": current_status.get('failed_count', 0)
                        }
                        yield f"event: status_update\ndata: {json.dumps(status_update, default=str)}\n\n"

                        complete_data = {
                            'event': 'complete',
                            'message': 'Process completed',
                            'download_url': current_status.get('download_url'),
                            'labels_only_url': current_status.get('labels_only_url'),
                            'report_url': current_status.get('report_url'),
                            'status': current_status.get('status'),
                            'successful': current_status.get('successful', 0),
                            'failed': current_status.get('failed', 0),
                            'total': current_status.get('total', 0),
                            'failed_orders': current_status.get('failed_orders', []),
                            'failed_count': current_status.get('failed_count', 0)
                        }
                        yield f"event: complete\ndata: {json.dumps(complete_data, default=str)}\n\n"
                        break

                    # Heartbeat
                    yield f"event: ping\ndata: {json.dumps({'timestamp': str(datetime.utcnow())})}\n\n"
                except Exception:
                    break

        finally:
            sse_manager.disconnect(str(process_id), queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.get("/process/{process_id}/status")
async def get_process_status_live(
    process_id: int,
    current_user = Depends(deps.get_current_user),
    db = Depends(deps.get_db)
):
    """Get current process status without streaming."""
    service = OrderService(db)
    status = await service.get_process_status(process_id, current_user.id)
    return status
