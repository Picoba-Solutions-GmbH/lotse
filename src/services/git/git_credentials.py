"""Access tokens of Git sources, stored as Kubernetes secrets."""
from src.services import secret_store

_TOKEN_KEY = "token"


def secret_name_for(source_id: str) -> str:
    return f"lotse-git-{source_id}"


def store_token(source_id: str, token: str) -> str:
    """Creates or replaces the secret of a source. Returns the secret name."""
    return secret_store.upsert(secret_name_for(source_id), secret_store.OPAQUE, {_TOKEN_KEY: token},
                               labels={"lotse/git-source": source_id})


def read_token(secret_name: str | None) -> str | None:
    data = secret_store.read(secret_name)
    return data.get(_TOKEN_KEY) if data else None


def delete_token(secret_name: str | None) -> None:
    secret_store.delete(secret_name)
