def registry_secret_name(registry_id: str) -> str:
    """kubernetes.io/dockerconfigjson secret with the credentials of a registry. Also used as pull secret."""
    return f"lotse-registry-{registry_id}"
