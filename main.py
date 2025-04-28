import logging
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

import src.utils.service_registry as service_registry
from src.models.database_access import init_db
from src.routes import execute, package, proxy, status, task
from src.routes.proxy import handle_proxy_404_middleware
from src.services.activemq_service import ActiveMQService
from src.services.kubernetes.k8s_manager_service import K8sManagerService
from src.utils import config
from src.utils.singleton_meta import get_service_instance

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized")
    service_registry.initialize_registry()

    k8s_manager_service = get_service_instance(K8sManagerService)
    await k8s_manager_service.check_and_initialize_pods()

    if config.ACTIVEMQ_ACTIVE:
        logger.info("Starting ActiveMQ listener...")
        threading.Thread(target=get_service_instance(ActiveMQService).start_listener, daemon=True).start()
    yield

app = FastAPI(title=config.APP_NAME, root_path=config.OPENAPI_PREFIX_PATH,
              version=config.API_VERSION, lifespan=lifespan)

app.middleware('http')(handle_proxy_404_middleware)


@app.get("/ui", include_in_schema=False)
@app.get("/ui{full_path:path}", include_in_schema=False)
async def serve_angular(full_path: str):
    file_path = os.path.join("ui", full_path.lstrip("/"))
    if os.path.exists(file_path) and not os.path.isdir(file_path):
        return FileResponse(file_path)

    return FileResponse("ui/index.html")


app.include_router(status.router)
app.include_router(task.router)
app.include_router(execute.router)
app.include_router(package.router)
app.include_router(proxy.router)
app.include_router(proxy.vscode_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def tracking_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    duration_text = f"{duration:.2f}s"
    logger.info(f"{request.method} {request.url} {response.status_code} {duration_text}",
                extra={'method': request.method, 'url': request.url, 'statusCode': response.status_code,
                       'duration': duration_text, 'msgType': 'Request'})

    return response


async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        logger.exception(f"An unhandled exception occurred {e}")
        response = PlainTextResponse(str(e), status_code=500)
        e.__traceback__ = None
        return response


app.middleware('http')(catch_exceptions_middleware)
app.middleware('http')(tracking_middleware)
