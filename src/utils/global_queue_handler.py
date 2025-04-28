import asyncio
import os
import threading
import uuid
from typing import Any, Callable, Dict, List, Optional, Union

cpu_count = os.cpu_count() or 4


class TaskQueue:
    def __init__(self, max_concurrent=min(8, cpu_count + 4)):
        self._lock = threading.Lock()
        self.max_concurrent = max_concurrent
        self.tasks: Dict[str, asyncio.Task] = {}
        self.results: Dict[str, Any] = {}
        self.queue = None
        self.semaphore = None
        self.loop = None
        self.loop_thread = None
        self.loop_thread_id = None
        self.queue_processor = None
        self._initialize_loop()

    def _run_event_loop(self, loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def _initialize_loop(self):
        with self._lock:
            if self.loop is None or self.loop.is_closed():
                self.loop = asyncio.new_event_loop()
                self.loop_thread = threading.Thread(target=self._run_event_loop, args=(self.loop,), daemon=True)
                self.loop_thread.start()
                self.loop_thread_id = self.loop_thread.ident

            if self.queue is None:
                self.queue = asyncio.Queue()

            if self.semaphore is None:
                self.semaphore = asyncio.Semaphore(self.max_concurrent)

            if self.queue_processor is None or (hasattr(self.queue_processor, 'done') and self.queue_processor.done()):
                future = asyncio.run_coroutine_threadsafe(self.process_queue(), self.loop)
                self.queue_processor = future

    def enqueue(self, func: Callable, *args, **kwargs) -> Union[str, str]:
        if self.loop is None or self.loop.is_closed():
            self._initialize_loop()
        if self.loop is None or self.queue is None:
            raise RuntimeError("Event loop is not initialized.")
        task_id = str(uuid.uuid4())

        asyncio.run_coroutine_threadsafe(
            self.queue.put((task_id, func, args, kwargs)),
            self.loop
        )
        return task_id

    async def process_queue(self):
        while True:
            try:
                if self.queue is None:
                    raise RuntimeError("Queue is not initialized.")
                task_id, func, args, kwargs = await self.queue.get()
                self.tasks[task_id] = asyncio.create_task(self._execute_task(task_id, func, args, kwargs))
                self.queue.task_done()
            except Exception as e:
                print(f"Error in process_queue: {e}")
                await asyncio.sleep(1)

    async def _execute_task(self, task_id, func, args, kwargs):
        if self.semaphore is None:
            raise RuntimeError("Semaphore is not initialized.")
        async with self.semaphore:
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = await asyncio.to_thread(func, *args, **kwargs)
                self.results[task_id] = {"status": "completed", "result": result}
            except Exception as e:
                self.results[task_id] = {"status": "failed", "error": str(e)}
            finally:
                if task_id in self.tasks:
                    del self.tasks[task_id]

    async def wait_for_tasks(self, task_ids: List[str], timeout: Optional[float] = None) -> Dict[str, Any]:
        pending = set(task_ids)
        results = {}
        end_time = None if timeout is None else asyncio.get_event_loop().time() + timeout
        while pending:
            if end_time and asyncio.get_event_loop().time() >= end_time:
                break
            completed = set()
            for task_id in pending:
                if task_id in self.results:
                    completed.add(task_id)
                    results[task_id] = self.results[task_id]
            pending -= completed
            if pending:
                await asyncio.sleep(0.1)
        return results


class GlobalQueueHandlerSingleton:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = TaskQueue()
        return cls._instance
