import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.progress import subscribe_progress

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()
    pubsub = subscribe_progress(job_id)

    try:
        loop = asyncio.get_event_loop()

        while True:
            # Run blocking pubsub.get_message in thread pool to avoid blocking event loop
            message = await loop.run_in_executor(
                None, lambda: pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            )

            if message and message["type"] == "message":
                data = json.loads(message["data"])
                await websocket.send_json(data)

                # Close connection when job reaches terminal state
                if data.get("status") in ("done", "error"):
                    break
            else:
                # Send heartbeat to keep connection alive
                try:
                    await asyncio.wait_for(
                        websocket.send_json({"type": "heartbeat"}), timeout=1.0
                    )
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    finally:
        pubsub.unsubscribe()
        pubsub.close()
        try:
            await websocket.close()
        except Exception:
            pass
