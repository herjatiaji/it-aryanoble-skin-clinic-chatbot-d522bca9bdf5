import asyncio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.core.broadcaster import broadcaster

router = APIRouter()

@router.get("/sync")
async def sync_events():
    async def event_generator():
        queue = await broadcaster.subscribe()
        try:
            # Yield initial comment so the client/proxy immediately receives the HTTP 200 stream
            yield ": connected\n\n"
            while True:
                try:
                    # Wait for broadcast messages with a 15-second heartbeat timeout
                    message = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {message}\n\n"
                except asyncio.TimeoutError:
                    # Send periodic SSE comment to keep TCP connection alive
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            broadcaster.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream",
        }
    )

