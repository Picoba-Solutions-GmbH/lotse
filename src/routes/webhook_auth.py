import hashlib
import hmac
import secrets

from fastapi import HTTPException, Request


async def require_webhook_token(request: Request, expected: str | None) -> None:
    """Webhook authentication, one of:
    - header `X-Lotse-Token: <token>` (Azure DevOps, ACR, GitLab, curl)
    - webhook secret = token, signed body in `X-Hub-Signature-256` (GitHub, Gitea)
    - query parameter `?token=<token>` (Docker Hub, which can't send headers)

    `expected` None (unknown source) fails the same way as a wrong token.
    """
    known = expected is not None
    expected = expected or secrets.token_urlsafe(24)

    token = request.headers.get("x-lotse-token") or request.query_params.get("token")
    signature = request.headers.get("x-hub-signature-256")
    if token:
        valid = hmac.compare_digest(token.encode(), expected.encode())
    elif signature:
        body = await request.body()
        digest = "sha256=" + hmac.new(expected.encode(), body, hashlib.sha256).hexdigest()
        valid = hmac.compare_digest(signature.encode(), digest.encode())
    else:
        valid = False

    if not known or not valid:
        raise HTTPException(status_code=401, detail="Invalid webhook token")
