import logging
from typing import Callable, TypeVar

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from src.services.git.git_client import GitError
from src.services.registry.registry_client import RegistryError
from src.services.sync.common import (SourceBusyError, SyncConfigError,
                                      describe_error)

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def call_sync(function: Callable[..., T], *args) -> T:
    """Runs blocking Git/registry/sync calls in a worker thread and maps their errors to HTTP errors."""
    try:
        return await run_in_threadpool(function, *args)
    except HTTPException:
        raise
    except SourceBusyError:
        raise HTTPException(status_code=409, detail="A check or sync of this source is already running")
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SyncConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GitError as e:
        raise HTTPException(status_code=502, detail=f"Git: {e}")
    except RegistryError as e:
        raise HTTPException(status_code=502, detail=f"Registry: {e}")
    except Exception as e:
        logger.exception("Sync operation failed")
        raise HTTPException(status_code=500, detail=describe_error(e))
