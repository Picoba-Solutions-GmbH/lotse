import asyncio
import os
from enum import Enum
from typing import Optional, TypeVar

import httpx
import websockets
from fastapi import APIRouter, BackgroundTasks, Request, WebSocket
from fastapi.responses import StreamingResponse

from src.database.models.task_entity import TaskEntity
from src.database.repositories.task_repository import TaskRepository
from src.utils import config
from src.utils.singleton_meta import get_service, get_service_instance


class ProxyCacheType(Enum):
    PROXY = "proxy"
    VSCODE = "vscode"


router = APIRouter(prefix="/proxy", include_in_schema=False)
vscode_router = APIRouter(prefix="/vscode", include_in_schema=False)

_proxy_task_id_cache = {}
_vscode_task_id_cache = {}

T = TypeVar('T')


def get_task_info(task_id: str, task_manager: TaskRepository, cache_type: ProxyCacheType) -> Optional[dict]:
    cache_map = {
        ProxyCacheType.PROXY: (_proxy_task_id_cache, lambda t: t.ui_port if isinstance(t, TaskEntity) else None),
        ProxyCacheType.VSCODE: (_vscode_task_id_cache, lambda t: t.vscode_port if isinstance(t, TaskEntity) else None)
    }

    cache, port_getter = cache_map[cache_type]

    if task_id not in cache:
        task = task_manager.get_task(task_id)
        if not task:
            return None

        port = port_getter(task)
        if not port:
            return None

        cache[task_id] = {
            'port': port,
            'ip': task.ui_ip_address
        }

    return cache[task_id]


def generate_prefix_suffix(task_id: str, request: Request, cache_type: ProxyCacheType):
    if cache_type.value in request.url.path:
        prefix = request.url.path[:request.url.path.find(f"{task_id}/") + len(f"{task_id}")]
        suffix = request.url.path[request.url.path.find(f"{task_id}/") + len(f"{task_id}/"):]
    else:
        prefix = f"{config.OPENAPI_PREFIX_PATH}/{cache_type.value}/{task_id}"
        suffix = request.url.path.replace(config.OPENAPI_PREFIX_PATH, "")

    return prefix, suffix


async def _handle_proxy_request(request: Request,
                                task_id: str,
                                task_manager: TaskRepository,
                                proxy_type: ProxyCacheType):
    HTTP_SERVER = None
    try:
        task_info = get_task_info(task_id, task_manager, proxy_type)
        if task_info is None:
            return StreamingResponse("Task not found", status_code=404)

        prefix, suffix = generate_prefix_suffix(task_id, request, proxy_type)

        address = task_info['ip'] if not config.IS_DEBUG else "localhost"
        port = task_info['port']

        url = httpx.URL(path=suffix, query=request.url.query.encode("utf-8"))

        if not config.IS_DEBUG:
            ip = address.split(":")[0]
            no_proxy = os.environ.get("no_proxy", "").split(",")

            if ip not in no_proxy:
                no_proxy.append(ip)
                os.environ["no_proxy"] = ",".join(no_proxy)

        base_url = f"http://{address}:{port}/"
        HTTP_SERVER = httpx.AsyncClient(base_url=base_url, cookies=request.cookies,
                                        follow_redirects=True)

        headers = dict(request.headers.raw)
        headers[b'X-Forwarded-Prefix'] = prefix.encode()
        reverse_proxy_request = HTTP_SERVER.build_request(
            request.method, url,
            headers=headers,
            content=await request.body()
        )

        reverse_proxy_response = await HTTP_SERVER.send(reverse_proxy_request, stream=True)

        tasks = BackgroundTasks()
        tasks.add_task(reverse_proxy_response.aclose)

        return StreamingResponse(
            reverse_proxy_response.aiter_raw(),
            status_code=reverse_proxy_response.status_code,
            headers=reverse_proxy_response.headers,
            background=tasks)
    except Exception as e:
        print(f"Proxy error: {e}")
        if HTTP_SERVER and not HTTP_SERVER.is_closed:
            await HTTP_SERVER.aclose()
        return StreamingResponse("Proxy error", status_code=500)


@router.api_route("/{task_id}/{path:path}", methods=["GET", "POST"])
async def _reverse_proxy(task_id: str,
                         request: Request,
                         task_manager: TaskRepository = get_service(TaskRepository)):
    return await _handle_proxy_request(request, task_id, task_manager, ProxyCacheType.PROXY)


@vscode_router.api_route("/{task_id}/{path:path}", methods=["GET", "POST"])
async def _vscode_proxy(task_id: str,
                        request: Request,
                        task_manager: TaskRepository = get_service(TaskRepository)):
    return await _handle_proxy_request(request, task_id, task_manager, ProxyCacheType.VSCODE)


async def _handle_websocket_proxy(websocket: WebSocket, task_id: str, path: str,
                                  task_manager: TaskRepository,
                                  cache_type: ProxyCacheType):
    task_info = get_task_info(task_id, task_manager, cache_type)
    if task_info is None:
        await websocket.close(code=1008, reason="Task not found")
        return StreamingResponse("Task not found", status_code=404)

    address_to_use = task_info['ip'] if not config.IS_DEBUG else "localhost"

    ws_protocol = None
    if "sec-websocket-protocol" in websocket.headers:
        ws_protocol = websocket.headers["sec-websocket-protocol"]
        if "," in ws_protocol:
            ws_protocol = ws_protocol.split(",")[0].strip()

    await websocket.accept(subprotocol=ws_protocol)

    port = task_info['port']
    query_string = websocket.scope.get("query_string", b"").decode()
    target_url = f"ws://{address_to_use}:{port}/{path}"
    if query_string:
        target_url += f"?{query_string}"

    try:
        async with websockets.connect(target_url) as target_ws:
            forward_client_to_server = asyncio.create_task(
                forward_ws(websocket, target_ws, "client → server")
            )

            forward_server_to_client = asyncio.create_task(
                forward_ws(target_ws, websocket, "server → client")
            )

            _, pending = await asyncio.wait(
                [forward_client_to_server, forward_server_to_client],
                return_when=asyncio.FIRST_COMPLETED
            )

            for task in pending:
                task.cancel()

    except Exception as e:
        print(f"WebSocket proxy error: {e}")
        await websocket.close(code=1011, reason=str(e))


@router.websocket("/{task_id}/{path:path}")
async def websocket_proxy(
    websocket: WebSocket,
    task_id: str,
    path: str,
    task_manager: TaskRepository = get_service(TaskRepository)
):
    await _handle_websocket_proxy(websocket, task_id, path, task_manager, ProxyCacheType.PROXY)


@vscode_router.websocket("/{task_id}/{path:path}")
async def vscode_websocket_proxy(
    websocket: WebSocket,
    task_id: str,
    path: str,
    task_manager: TaskRepository = get_service(TaskRepository)
):
    await _handle_websocket_proxy(websocket, task_id, path, task_manager, ProxyCacheType.VSCODE)


async def forward_ws(source, destination, direction):
    try:
        if isinstance(source, WebSocket):
            while True:
                message = await source.receive()
                if "text" in message:
                    await destination.send(message["text"])
                elif "bytes" in message:
                    await destination.send(message["bytes"])
        else:
            while True:
                message = await source.recv()
                if isinstance(message, str):
                    await destination.send_text(message)
                else:
                    await destination.send_bytes(message)
    except Exception as e:
        print(f"Error in {direction}: {e}")
        raise


async def proxy_404_forwarder(
        request: Request,
        referer: str) -> Optional[StreamingResponse]:
    task_manager = get_service_instance(TaskRepository)
    cache_type_map = {
        "/proxy/": ProxyCacheType.PROXY,
        "/vscode/": ProxyCacheType.VSCODE
    }
    cache_type = next((ct for path, ct in cache_type_map.items() if path in referer), None)
    if not cache_type:
        return None

    if f"/{cache_type.value}/" in referer and not request.url.path.startswith(f"/{cache_type.value}/"):
        referer_parts = referer.split(f"/{cache_type.value}/")[1].split("/")
        if referer_parts:
            task_id = referer_parts[0]
            proxy_response = await _handle_proxy_request(request, task_id, task_manager, cache_type)
            return proxy_response


async def handle_proxy_404_middleware(request: Request, call_next):
    if "referer" not in request.headers:
        return await call_next(request)

    referer = request.headers["referer"]

    if not any(cache_type.value in referer for cache_type in ProxyCacheType):
        return await call_next(request)

    response = await call_next(request)
    if response.status_code == 404:
        return await proxy_404_forwarder(request, referer)

    return response
