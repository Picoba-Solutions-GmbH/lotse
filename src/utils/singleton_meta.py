from typing import Type, TypeVar

from fastapi import Depends

T = TypeVar('T')


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


def get_service(service_class: Type[T]) -> T:
    def _get_instance() -> T:
        return service_class()
    return Depends(_get_instance)


def get_service_instance(service_class: Type[T]) -> T:
    return service_class()
