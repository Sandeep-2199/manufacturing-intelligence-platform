"""Send team administrator recovery links using the configured email service."""

import json
import logging
import os
from urllib.error import URLError
from urllib.request import Request, urlopen


def recovery_email():
    if os.getenv("RESEND_API_KEY") and os.getenv("MIP_RECOVERY_FROM") and os.getenv("RENDER_EXTERNAL_URL"):
        return os.getenv("MIP_TEAMADMIN_RECOVERY_EMAIL")
    return None


def send_reset_email(recipient: str, token: str) -> bool:
    origin = os.environ["RENDER_EXTERNAL_URL"].rstrip("/")
    link = f"{origin}/dashboard/#reset={token}"
    request = Request(
        "https://api.resend.com/emails",
        data=json.dumps({
            "from": os.environ["MIP_RECOVERY_FROM"],
            "to": [recipient],
            "subject": "Reset your Manufacturing Intelligence password",
            "text": f"Open this link within 20 minutes to reset your password:\n\n{link}",
        }).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
            "Content-Type": "application/json",
            "User-Agent": "Manufacturing-Intelligence",
        },
    )
    try:
        with urlopen(request, timeout=5):
            return True
    except (URLError, TimeoutError):
        logging.getLogger(__name__).warning("Could not deliver the administrator password reset email.")
        return False
