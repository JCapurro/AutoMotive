"""Small, bundled brand asset embedded via CID (no public asset deployment)."""
from base64 import b64encode
from functools import cache
from pathlib import Path


LOGO_CONTENT_ID = "ese-auto-logo"


@cache
def _logo_content() -> str:
    return b64encode((Path(__file__).parent / "assets" / "ese-auto-logo.png").read_bytes()).decode("ascii")


def logo_attachment() -> dict[str, str]:
    return {"filename": "ese-auto-logo.png", "content_type": "image/png",
            "content_id": LOGO_CONTENT_ID, "content": _logo_content()}
