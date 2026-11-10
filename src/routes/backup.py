import json
import logging
import os
import shutil
import socket
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from kubernetes import client
from pydantic import BaseModel
from starlette.background import BackgroundTask
from sqlalchemy.orm import Session

from src.authentication.schemas_authentication import CurrentUser
from src.database.database_access import get_db_session
from src.database.models.package_entity import PackageEntity
from src.database.repositories.package_repository import PackageRepository
from src.database.repositories.package_share_repository import PackageShareRepository
from src.database.repositories.user_repository import UserRepository
from src.misc.runtime_type import RuntimeType
from src.models.yaml_config import parse_config
from src.routes import authentication
from src.utils import config
from src.utils.name_generator import sanitize_name
from src.utils.path_manager import PathManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backup", tags=["backup"])

LIVE_VERSION = "live"
SERVICE_ACCOUNT_NAMESPACE_FILE = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
POD_WORKDIR = "/app"


class BackupSelection(BaseModel):
    package_name: str
    versions: list[str] | None = None


class BackupRequest(BaseModel):
    packages: list[BackupSelection] | None = None
    include_config: bool = True
    only_active: bool = False


def _path_size(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    if path.is_file():
        return path.stat().st_size, 1

    total, count = 0, 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
                count += 1
            except OSError:
                pass
    return total, count


def _is_inside(path: Path, root: str) -> bool:
    try:
        path.resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def _archive_name(package: PackageEntity) -> str:
    return f"{package.package_name}.7z"


def _runtime_of(package: PackageEntity) -> tuple[RuntimeType | None, str | None]:
    try:
        package_config = parse_config(package.config)  # type: ignore
        return package_config.runtime, package_config.image
    except Exception:  # pylint: disable=broad-except
        return None, None


def _describe_version(package: PackageEntity) -> dict:
    runtime, image = _runtime_of(package)
    package_dir = PathManager.get_package_path(package.package_name, package.version)  # type: ignore
    venv_dir = PathManager.get_venv_path(package.package_name, package.version)  # type: ignore
    archive_path = package_dir / _archive_name(package)

    size, file_count = _path_size(package_dir)
    venv_size, _ = _path_size(venv_dir)

    return {
        "package_name": package.package_name,
        "version": package.version,
        "deployment_id": package.deployment_id,
        "deployed_at": package.deployed_at.isoformat() if package.deployed_at else None,  # type: ignore
        "active": bool(package.active),
        "is_live": package.version == LIVE_VERSION,
        "description": package.description,
        "runtime": runtime.value if runtime else None,
        "image": image,
        "path": str(package_dir),
        "exists": package_dir.exists(),
        "size_bytes": size,
        "file_count": file_count,
        "has_archive": archive_path.is_file(),
        "archive_size_bytes": archive_path.stat().st_size if archive_path.is_file() else 0,
        "venv_path": str(venv_dir),
        "venv_exists": venv_dir.exists(),
        "venv_size_bytes": venv_size,
    }


def _find_orphans(packages: list[PackageEntity]) -> list[dict]:
    known = {(sanitize_name(p.package_name), p.version) for p in packages}  # type: ignore
    orphans = []
    root = Path(config.PACKAGES_ROOT)
    if not root.exists():
        return orphans

    for package_dir in sorted(root.iterdir()):
        if not package_dir.is_dir():
            continue
        for version_dir in sorted(package_dir.iterdir()):
            if version_dir.is_dir() and (package_dir.name, version_dir.name) not in known:
                size, file_count = _path_size(version_dir)
                orphans.append({
                    "directory": f"{package_dir.name}/{version_dir.name}",
                    "path": str(version_dir),
                    "size_bytes": size,
                    "file_count": file_count,
                })
    return orphans


def _own_namespace() -> str | None:
    try:
        with open(SERVICE_ACCOUNT_NAMESPACE_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def _describe_persistent_volume(v1: client.CoreV1Api, pv_name: str) -> dict:
    pv = v1.read_persistent_volume(pv_name)
    spec = pv.spec
    source = None
    if spec.host_path:
        source = {"type": "hostPath", "location": spec.host_path.path}
    elif spec.local:
        source = {"type": "local", "location": spec.local.path}
    elif spec.nfs:
        source = {"type": "nfs", "location": f"{spec.nfs.server}:{spec.nfs.path}"}
    elif spec.csi:
        source = {"type": "csi", "location": f"{spec.csi.driver} ({spec.csi.volume_handle})"}
    elif spec.azure_file:
        source = {"type": "azureFile", "location": spec.azure_file.share_name}
    elif spec.azure_disk:
        source = {"type": "azureDisk", "location": spec.azure_disk.disk_name}

    node_affinity = None
    if spec.node_affinity and spec.node_affinity.required:
        nodes = []
        for term in spec.node_affinity.required.node_selector_terms or []:
            for expression in term.match_expressions or []:
                nodes.extend(expression.values or [])
        node_affinity = nodes or None

    return {
        "pv_name": pv_name,
        "reclaim_policy": spec.persistent_volume_reclaim_policy,
        "source": source,
        "nodes": node_affinity,
    }


def _describe_kubernetes_storage() -> dict | None:
    if not os.getenv("KUBERNETES_SERVICE_HOST"):
        return None

    namespace = _own_namespace()
    pod_name = os.getenv("HOSTNAME") or socket.gethostname()
    result: dict = {"namespace": namespace, "pod_name": pod_name, "node_name": None, "volume": None}
    if not namespace:
        return result

    try:
        v1 = client.CoreV1Api()
        pod = v1.read_namespaced_pod(pod_name, namespace)
        result["node_name"] = pod.spec.node_name

        home = str(config.HOME_PATH).replace("\\", "/")
        mount = None
        for container in pod.spec.containers:
            for volume_mount in container.volume_mounts or []:
                mount_path = volume_mount.mount_path.rstrip("/")
                if home == mount_path or home.startswith(mount_path + "/"):
                    if mount is None or len(mount_path) > len(mount.mount_path):
                        mount = volume_mount
        if mount is None:
            return result

        volume = next((v for v in pod.spec.volumes or [] if v.name == mount.name), None)
        volume_info: dict = {"name": mount.name, "mount_path": mount.mount_path, "pvc_name": None}
        if volume is not None and volume.persistent_volume_claim:
            pvc_name = volume.persistent_volume_claim.claim_name
            pvc = v1.read_namespaced_persistent_volume_claim(pvc_name, namespace)
            volume_info.update({
                "pvc_name": pvc_name,
                "storage_class": pvc.spec.storage_class_name,
                "access_modes": pvc.spec.access_modes,
                "capacity": (pvc.status.capacity or {}).get("storage") if pvc.status else None,
                "phase": pvc.status.phase if pvc.status else None,
            })
            if pvc.spec.volume_name:
                try:
                    volume_info["persistent_volume"] = _describe_persistent_volume(v1, pvc.spec.volume_name)
                except Exception as e:  # pylint: disable=broad-except
                    logger.debug("Could not read persistent volume %s: %s", pvc.spec.volume_name, e)
        elif volume is not None and volume.host_path:
            volume_info["host_path"] = volume.host_path.path
        elif volume is not None and volume.empty_dir is not None:
            volume_info["empty_dir"] = True
        result["volume"] = volume_info
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("Could not determine kubernetes storage of the lotse pod: %s", e)
        result["error"] = str(e)

    return result


@router.get("/storage")
async def get_storage_overview(
    db: Session = Depends(get_db_session),
    _: CurrentUser = Depends(authentication.require_admin),
):
    packages = PackageRepository.list_packages(db)
    owner_map = PackageShareRepository.get_owner_map(db)
    user_names = {u.id: (u.display_name or u.name) for u in UserRepository.list_users(db)}

    def build() -> dict:
        grouped: dict[str, list[dict]] = {}
        for package in packages:
            grouped.setdefault(package.package_name, []).append(_describe_version(package))  # type: ignore

        package_list = []
        for package_name in sorted(grouped, key=str.lower):
            versions = sorted(grouped[package_name], key=lambda v: v["deployed_at"] or "", reverse=True)
            package_list.append({
                "package_name": package_name,
                "owner": user_names.get(owner_map.get(package_name)),  # type: ignore
                "path": str(Path(config.PACKAGES_ROOT) / sanitize_name(package_name)),
                "size_bytes": sum(v["size_bytes"] for v in versions),
                "venv_size_bytes": sum(v["venv_size_bytes"] for v in versions),
                "versions": versions,
            })

        disk = None
        try:
            usage = shutil.disk_usage(config.PACKAGES_ROOT)
            disk = {"total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}
        except OSError:
            pass

        orphans = _find_orphans(packages)
        return {
            "location": {
                "hostname": socket.gethostname(),
                "in_cluster": bool(os.getenv("KUBERNETES_SERVICE_HOST")),
                "home_path": str(config.HOME_PATH),
                "packages_root": str(config.PACKAGES_ROOT),
                "venvs_root": str(config.VENVS_ROOT),
                "execution_namespace": config.K8S_NAMESPACE,
                "execution_workdir": POD_WORKDIR,
                "disk": disk,
                "kubernetes": _describe_kubernetes_storage(),
            },
            "totals": {
                "packages": len(package_list),
                "versions": sum(len(p["versions"]) for p in package_list),
                "size_bytes": sum(p["size_bytes"] for p in package_list),
                "venv_size_bytes": sum(p["venv_size_bytes"] for p in package_list),
                "orphan_size_bytes": sum(o["size_bytes"] for o in orphans),
            },
            "packages": package_list,
            "orphans": orphans,
        }

    return await run_in_threadpool(build)


def _select_packages(db: Session, request: BackupRequest) -> list[PackageEntity]:
    all_packages = PackageRepository.list_packages(db)
    if request.packages is None:
        selected = all_packages
    else:
        by_name: dict[str, list[PackageEntity]] = {}
        for package in all_packages:
            by_name.setdefault(package.package_name, []).append(package)  # type: ignore

        selected = []
        for selection in request.packages:
            versions = by_name.get(selection.package_name)
            if not versions:
                raise HTTPException(status_code=404, detail=f"Package {selection.package_name} not found")
            if selection.versions is None:
                selected.extend(versions)
                continue
            for version in selection.versions:
                match = next((p for p in versions if p.version == version), None)
                if match is None:
                    raise HTTPException(
                        status_code=404, detail=f"Package {selection.package_name} version {version} not found")
                selected.append(match)

    if request.only_active:
        selected = [p for p in selected if p.active]

    # de-duplicate while keeping the order
    unique = {p.deployment_id: p for p in selected}
    return list(unique.values())


def _write_zip(zip_path: str, packages: list[PackageEntity], request: BackupRequest,
               owner_names: dict[str, str | None], generated_by: str) -> None:
    manifest_entries = []
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for package in packages:
            folder = f"{sanitize_name(package.package_name)}/{package.version}"  # type: ignore
            package_dir = PathManager.get_package_path(package.package_name, package.version)  # type: ignore
            runtime, image = _runtime_of(package)
            archive_name = _archive_name(package)
            has_archive = (package_dir / archive_name).is_file()

            # the originally uploaded archive is backed up. Live packages and old deployments have
            # no archive, their extracted files are backed up instead.
            content = "archive" if has_archive else "files"
            # files edited after the deployment are backed up next to the archive, extracting the
            # archive and copying them over it restores the current state
            modified_files = set(package.modified_files or [])  # type: ignore

            files_written = 0
            if package_dir.is_dir() and _is_inside(package_dir, config.PACKAGES_ROOT):
                for root, _, files in os.walk(package_dir):
                    for name in files:
                        full_path = Path(root) / name
                        relative = full_path.relative_to(package_dir).as_posix()
                        is_archive = relative == archive_name
                        if content == "archive" and not is_archive and relative not in modified_files:
                            continue
                        if request.include_config and relative == "config.yaml":
                            # the deployed config.yaml from the database takes precedence
                            continue
                        zf.write(full_path, f"{folder}/{relative}")
                        files_written += 1

            if request.include_config and package.config:
                zf.writestr(f"{folder}/config.yaml", package.config)  # type: ignore
                if package.config_modified:
                    zf.writestr(f"{folder}/config.original.yaml", package.original_config)  # type: ignore

            manifest_entries.append({
                "package_name": package.package_name,
                "version": package.version,
                "folder": folder,
                "deployment_id": package.deployment_id,
                "deployed_at": package.deployed_at.isoformat() if package.deployed_at else None,  # type: ignore
                "active": bool(package.active),
                "description": package.description,
                "runtime": runtime.value if runtime else None,
                "image": image,
                "owner": owner_names.get(package.package_name),  # type: ignore
                "content": content,
                "files": files_written,
                "config_included": bool(request.include_config and package.config),
                "config_modified": package.config_modified,
                "modified_files": sorted(modified_files),
                "source_path": str(package_dir),
            })

        manifest = {
            "generated_at": datetime.now().isoformat(),
            "generated_by": generated_by,
            "lotse_version": config.API_VERSION,
            "hostname": socket.gethostname(),
            "packages_root": str(config.PACKAGES_ROOT),
            "options": {
                "include_config": request.include_config,
                "only_active": request.only_active,
            },
            "packages": manifest_entries,
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))


def _zip_file_name(request: BackupRequest, packages: list[PackageEntity]) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    names = {p.package_name for p in packages}
    if request.packages is None:
        scope = "all-packages"
    elif len(names) == 1:
        name = sanitize_name(next(iter(names)))  # type: ignore
        scope = f"{name}-{packages[0].version}" if len(packages) == 1 else name
    else:
        scope = f"{len(names)}-packages"
    return f"lotse-backup-{scope}-{timestamp}.zip"


@router.post("/download")
async def download_backup(
    request: BackupRequest,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(authentication.require_admin),
):
    packages = _select_packages(db, request)
    if not packages:
        raise HTTPException(status_code=404, detail="No package versions match the selection")

    owner_map = PackageShareRepository.get_owner_map(db)
    user_names = {u.id: u.name for u in UserRepository.list_users(db)}
    owner_names = {name: user_names.get(owner_id) for name, owner_id in owner_map.items()}  # type: ignore

    fd, zip_path = tempfile.mkstemp(prefix="lotse-backup-", suffix=".zip")
    os.close(fd)
    try:
        await run_in_threadpool(_write_zip, zip_path, packages, request, owner_names, user.username)
    except Exception:
        os.remove(zip_path)
        raise

    file_name = _zip_file_name(request, packages)
    logger.info("User %s downloaded backup %s with %d package version(s)", user.username, file_name, len(packages))
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=file_name,
        background=BackgroundTask(os.remove, zip_path),
    )
