from __future__ import annotations

import os
from pathlib import Path

import boto3


def r2_client():
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET_KEY"],
        region_name="auto",
    )


def upload_mp3(path: Path, key: str) -> str:
    bucket = os.environ["R2_BUCKET"]
    public_base = os.environ["R2_PUBLIC_URL"].rstrip("/")
    r2_client().upload_file(
        str(path),
        bucket,
        key,
        ExtraArgs={"ContentType": "audio/mpeg"},
    )
    return f"{public_base}/{key}"

