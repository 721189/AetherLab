import uuid

from fastapi import Header, Request


def extract_request_id(
    request: Request,
    x_request_id: str | None = Header(default=None),
) -> str:
    """Resolve the inbound request ID, or generate a fresh one."""
    if x_request_id:
        return x_request_id
    return str(uuid.uuid4())
