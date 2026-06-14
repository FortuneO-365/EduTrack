# utils/azure.py
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from datetime import datetime, timedelta, timezone
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def get_blob_sas_url(blob_name: str, expiry_hours: int = 2) -> str | None:
    """
    Generate a temporary SAS URL for a private blob.
    Returns None if blob_name is empty or generation fails.
    """
    if not blob_name:
        return None

    # ── Strip full URL down to just the blob path ─────────────────
    # Handles the case where someone stored the full Azure URL
    # e.g. 'https://account.blob.core.windows.net/container/path/file.pdf'
    #  →   'path/file.pdf'
    if blob_name.startswith('https://') or blob_name.startswith('http://'):
        # Remove everything up to and including '/<container_name>/'
        try:
            # Split on the container name
            marker = f"/{settings.AZURE_CONTAINER}/"
            blob_name = blob_name.split(marker, 1)[1]
        except IndexError:
            logger.error(f"Could not parse blob path from URL: {blob_name}")
            return None

    # ── Strip leading slash if present ────────────────────────────
    blob_name = blob_name.lstrip('/')

    logger.debug(f"Generating SAS URL for blob: {blob_name}")

    try:
        sas_token = generate_blob_sas(
            account_name=settings.AZURE_ACCOUNT_NAME,
            container_name=settings.AZURE_CONTAINER,
            blob_name=blob_name,
            account_key=settings.AZURE_ACCOUNT_KEY,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
        )
        return (
            f"https://{settings.AZURE_ACCOUNT_NAME}"
            f".blob.core.windows.net"
            f"/{settings.AZURE_CONTAINER}"
            f"/{blob_name}?{sas_token}"
        )
    except Exception as e:
        logger.error(f"SAS URL generation failed for '{blob_name}': {e}")
        return None