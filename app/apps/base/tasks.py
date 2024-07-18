import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Coroutine, Literal, Union

from pydantic import BaseModel, Field
from singleton import Singleton
from utils import aionetwork, basic

from .schemas import BaseEntitySchema


class SignalRegistry(metaclass=Singleton):
    def __init__(self):
        self.signal_map: dict[
            str,
            list[Callable[..., None] | Callable[..., Coroutine[Any, Any, None]]],
        ] = {}


class TaskLogRecord(BaseModel):
    reported_at: datetime = Field(default_factory=datetime.now)
    message: str
    task_status: Literal["draft", "init", "processing", "done", "error"]
    duration: int = 0
    data: dict | None = None

    def __eq__(self, other):
        if isinstance(other, TaskLogRecord):
            return (
                self.reported_at == other.reported_at
                and self.message == other.message
                and self.task_status == other.task_status
                and self.duration == other.duration
                and self.data == other.data
            )
        return False

    def __hash__(self):
        return hash((self.reported_at, self.message, self.task_status, self.duration))


class TaskReference(BaseModel):
    task_id: uuid.UUID
    task_type: str

    def __eq__(self, other):
        if isinstance(other, TaskReference):
            return self.task_id == other.task_id and self.task_type == other.task_type
        return False

    def __hash__(self):
        return hash((self.task_id, self.task_type))

    async def get_task_item(self) -> BaseEntitySchema | None:
        task_classes = {
            subclass.__name__: subclass
            for subclass in basic.get_all_subclasses(TaskMixin)
            if issubclass(subclass, BaseEntitySchema)
        }
        # task_classes = self._get_all_task_classes()

        task_class = task_classes.get(self.task_type)
        if not task_class:
            raise ValueError(f"Task type {self.task_type} is not supported.")

        task_item = await task_class.find_one(task_class.uid == self.task_id)
        if not task_item:
            raise ValueError(
                f"No task found with id {self.task_id} of type {self.task_type}."
            )

        return task_item


class TaskReferenceList(BaseModel):
    tasks: list[Union[TaskReference, "TaskReferenceList"]] = []
    mode: Literal["serial", "parallel"] = "serial"

    async def list_processing(self):
        task_items = [task.get_task_item() for task in self.tasks]
        match self.mode:
            case "serial":
                for task_item in task_items:
                    await task_item.start_processing()
            case "parallel":
                await asyncio.gather(*[task.start_processing() for task in task_items])


class TaskMixin(BaseModel):
    task_status: Literal["draft", "init", "processing", "done", "error"] = "draft"
    task_report: str | None = None
    task_progress: int = -1
    task_logs: list[TaskLogRecord] = []
    task_references: TaskReferenceList | None = None

    @classmethod
    def signals(cls):
        registry = SignalRegistry()
        if cls.__name__ not in registry.signal_map:
            registry.signal_map[cls.__name__] = []
        return registry.signal_map[cls.__name__]

    @classmethod
    def add_signal(
        cls,
        signal: Callable[..., None] | Callable[..., Coroutine[Any, Any, None]],
    ):
        cls.signals().append(signal)

    @classmethod
    async def emit_signals(cls, task_instance, **kwargs):
        if task_instance.metadata:
            webhook = task_instance.metadata.get(
                "webhook"
            ) or task_instance.metadata.get("webhook_url")
            webhook_signals = [
                aionetwork.aio_request(
                    method="post",
                    url=webhook,
                    data=task_instance.model_dump_json(),
                )
            ]
        else:
            webhook_signals = []

        signals = webhook_signals + [
            (
                signal(task_instance)
                if asyncio.iscoroutinefunction(signal)
                else asyncio.to_thread(signal, task_instance)
            )
            for signal in cls.signals()
        ]

        await asyncio.gather(*signals)

    async def save_status(
        self,
        status: Literal["draft", "init", "processing", "done", "error"],
        **kwargs,
    ):
        self.task_status = status
        await self.add_log(
            TaskLogRecord(
                task_status=self.task_status,
                message=f"Status changed to {status}",
            ),
            **kwargs,
        )

    async def add_reference(self, task_id: uuid.UUID, **kwargs):
        self.task_references.append(task_id)
        await self.add_log(
            TaskLogRecord(
                task_status=self.task_status,
                message=f"Added reference to task {task_id}",
            ),
            **kwargs,
        )

    async def save_report(self, report: str, **kwargs):
        self.task_report = report
        await self.add_log(
            TaskLogRecord(
                task_status=self.task_status,
                message=report,
            ),
            **kwargs,
        )

    async def add_log(self, log_record: TaskLogRecord, *, emit: bool = True, **kwargs):
        self.task_logs.append(log_record)
        if emit:
            # await self.emit_signals(self)
            await self.save_and_emit()

    async def start_processing(self):
        if self.task_references is None:
            raise NotImplementedError("Subclasses should implement this method")

        await self.task_references.list_processing()

    async def save_and_emit(self):
        try:
            await asyncio.gather(self.save(), self.emit_signals(self))
        except Exception as e:
            logging.error(f"An error occurred: {e}")
