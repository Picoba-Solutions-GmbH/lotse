import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from kubernetes import client
from kubernetes.stream import stream

from src.services.kubernetes.pod_executor import PodExecutor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pod-terminal", tags=["pod-terminal"])


@router.websocket("/{namespace}/{pod_name}")
async def pod_terminal_websocket(
    websocket: WebSocket,
    namespace: str,
    pod_name: str
):
    resp = None
    output_task = None

    try:
        v1 = client.CoreV1Api()
        await websocket.accept()
        exec_command = PodExecutor.get_available_shell(v1, namespace, pod_name)

        resp = stream(
            v1.connect_get_namespaced_pod_exec,
            pod_name,
            namespace,
            command=exec_command,
            stderr=True,
            stdin=True,
            stdout=True,
            tty=True,
            _preload_content=False
        )

        async def read_output():
            try:
                while True:
                    if resp.peek_stdout():
                        output = resp.read_stdout()
                        await websocket.send_text(output)
                    if resp.peek_stderr():
                        error = resp.read_stderr()
                        await websocket.send_text(error)
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error in terminal output stream: {str(e)}")

        output_task = asyncio.create_task(read_output())

        while True:
            message = await websocket.receive_text()
            try:
                data = json.loads(message)
                if data.get("type") == "resize":
                    cols = data.get("cols", 80)
                    rows = data.get("rows", 24)
                    resp.write_channel(4, json.dumps({"Width": cols, "Height": rows}).encode())
                    continue
            except Exception:
                pass

            resp.write_stdin(message)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for pod {pod_name} in namespace {namespace}")
    except Exception as e:
        logger.error(f"Terminal WebSocket error: {str(e)}")
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close(code=4002, reason=str(e))
    finally:
        if output_task:
            output_task.cancel()
            try:
                await output_task
            except asyncio.CancelledError:
                pass

        if resp and resp.is_open():
            resp.close()

        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()
