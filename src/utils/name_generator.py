import hashlib
import re
import uuid


def generate_name(text: str) -> str:
    random_guid = str(uuid.uuid4())
    sha256_text = hashlib.sha256(random_guid.encode()).hexdigest()
    short_sha = sha256_text[:7]
    name = f"{text}-{short_sha}"
    name = name.lower()

    sanitized = re.sub(r'[^a-z0-9\.\-]', '-', name)

    sanitized = re.sub(r'^[^a-z0-9]+', '', sanitized)
    sanitized = re.sub(r'[^a-z0-9]+$', '', sanitized)

    if not sanitized:
        sanitized = "resource"

    if len(sanitized) > 253:
        sanitized = sanitized[:253]

    return sanitized
