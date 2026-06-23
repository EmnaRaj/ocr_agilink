import boto3
from botocore.client import Config

from ..config import settings


def _client():
    scheme = "https" if settings.minio_use_ssl else "http"
    return boto3.client(
        "s3",
        endpoint_url=f"{scheme}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_root_user,
        aws_secret_access_key=settings.minio_root_password,
        config=Config(signature_version="s3v4"),
    )


def upload_scan(key: str, data: bytes, content_type: str) -> str:
    _client().put_object(Bucket=settings.minio_bucket, Key=key, Body=data, ContentType=content_type)
    return f"s3://{settings.minio_bucket}/{key}"


def download_scan(storage_url: str) -> tuple[bytes, str]:
    """Fetch an object back from MinIO by its s3://bucket/key URL.

    Returns (bytes, content_type). Used to serve the original scan to the UI.
    """
    bucket, _, key = storage_url.removeprefix("s3://").partition("/")
    obj = _client().get_object(Bucket=bucket, Key=key)
    return obj["Body"].read(), obj.get("ContentType", "application/octet-stream")
