import asyncio
import logging
from typing import Any, Dict, Set

from fastapi import APIRouter, WebSocket
from fastapi.encoders import jsonable_encoder

from src.database.database_access import get_db_session
from src.database.repositories.task_repository import TaskRepository
from src.routes.package import get_package_by_version
from src.routes.task import get_task_logs
from src.services.task_manager_service import TaskManagerService
from src.utils.singleton_meta import get_service_instance

from . import cluster

router = APIRouter(prefix="/ws", tags=["websocket"])
logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.max_connections_per_type = 50
        self.last_broadcast: Dict[str, float] = {}
        self.min_broadcast_interval = 1.0

    async def connect(self, websocket: WebSocket, client_type: str):
        if client_type not in self.active_connections:
            self.active_connections[client_type] = set()

        if len(self.active_connections[client_type]) >= self.max_connections_per_type:
            await websocket.close(code=1008, reason="Too many connections")
            return

        await websocket.accept()
        self.active_connections[client_type].add(websocket)

    def disconnect(self, websocket: WebSocket, client_type: str):
        if client_type in self.active_connections and websocket in self.active_connections[client_type]:
            self.active_connections[client_type].remove(websocket)
            if not self.active_connections[client_type]:
                del self.active_connections[client_type]
                if client_type in self.last_broadcast:
                    del self.last_broadcast[client_type]

    def has_connections(self, client_type: str) -> bool:
        return client_type in self.active_connections and bool(self.active_connections[client_type])

    async def broadcast(self, data: Any, client_type: str) -> bool:
        if not self.has_connections(client_type):
            return False

        current_time = asyncio.get_event_loop().time()
        if client_type in self.last_broadcast:
            time_since_last = current_time - self.last_broadcast[client_type]
            if time_since_last < self.min_broadcast_interval:
                return True

        connections = list(self.active_connections[client_type])
        if not connections:
            return False

        json_data = jsonable_encoder(data)
        dead_connections = set()

        for connection in connections:
            if await self._safe_send(connection, json_data):
                self.last_broadcast[client_type] = current_time
            else:
                dead_connections.add(connection)

        if dead_connections:
            for dead in dead_connections:
                logger.warning(f"Removing dead connection for client_type {client_type}")
                self.disconnect(dead, client_type)

        return self.has_connections(client_type)

    async def _safe_send(self, connection: WebSocket, data: Any) -> bool:
        try:
            if connection.client_state.value != 1:
                logger.warning(f"Connection is not in CONNECTED state (state={connection.client_state})")
                return False

            await connection.send_json(data)
            return True
        except Exception as e:
            error_msg = str(e) if str(e) else e.__class__.__name__
            logger.error(f"Error sending data to websocket: {error_msg}")
            return False


manager = ConnectionManager()


async def get_cluster_data():
    return await cluster.get_nodes()


@router.websocket("/cluster")
async def websocket_cluster_endpoint(websocket: WebSocket):
    client_type = "cluster"
    await manager.connect(websocket, client_type)
    try:
        while True:
            try:
                data = await get_cluster_data()
                if not await manager.broadcast(data, client_type):
                    break

                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cluster websocket: {str(e)}")
                break
    finally:
        manager.disconnect(websocket, client_type)


@router.websocket("/namespace/{namespace}/{resource_type}")
async def websocket_namespace_resource_endpoint(
    websocket: WebSocket,
    namespace: str,
    resource_type: str
):
    client_type = f"namespace_{namespace}_{resource_type}"
    await manager.connect(websocket, client_type)

    resource_fetchers = {
        "pods": cluster.get_pods_for_namespace,
        "services": cluster.get_services_for_namespace,
        "deployments": cluster.get_deployments_for_namespace,
        "statefulsets": cluster.get_statefulsets_for_namespace,
        "configmaps": cluster.get_configmaps_for_namespace,
        "ingresses": cluster.get_ingresses_for_namespace,
        "pvcs": cluster.get_pvcs_for_namespace,
    }

    try:
        if resource_type not in resource_fetchers:
            await websocket.send_json({"error": f"Invalid resource type: {resource_type}"})
            return

        fetcher = resource_fetchers[resource_type]
        while True:
            try:
                data = await fetcher(namespace)
                if not await manager.broadcast({resource_type: data}, client_type):
                    break

                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in namespace resource websocket: {str(e)}")
                break
    finally:
        manager.disconnect(websocket, client_type)


@router.websocket("/task/{task_id}")
async def websocket_task_endpoint(websocket: WebSocket, task_id: str):
    client_type = f"task_{task_id}"
    await manager.connect(websocket, client_type)
    try:
        task_repository: TaskRepository = get_service_instance(TaskRepository)
        task_manager_service: TaskManagerService = get_service_instance(TaskManagerService)

        while True:
            try:
                task_logs = await get_task_logs(task_id, task_repository, task_manager_service)
                data = {**task_logs}
                if not await manager.broadcast(data, client_type):
                    break

                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Error in task websocket: {str(e)}")
                break
    finally:
        manager.disconnect(websocket, client_type)


@router.websocket("/{package_name}/{stage}/{version}")
async def websocket_package_instance_endpoint(websocket: WebSocket, package_name: str, stage: str, version: str):
    client_type = f"{package_name}_{stage}_{version}"
    await manager.connect(websocket, client_type)
    session = next(get_db_session())
    try:
        task_repository: TaskRepository = get_service_instance(TaskRepository)
        task_manager_service: TaskManagerService = get_service_instance(TaskManagerService)

        while True:
            try:
                package_instance = await get_package_by_version(
                    package_name, stage, version, session, task_repository, task_manager_service)
                data = {"tasks": package_instance.tasks}
                if not await manager.broadcast(data, client_type):
                    break

                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Error in package websocket: {str(e)}")
                break
    finally:
        session.close()
        manager.disconnect(websocket, client_type)
