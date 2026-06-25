from __future__ import annotations

import argparse
import re

from .storage import r2_client

PREFIX_RE = re.compile(r"^[a-z0-9][a-z0-9-]*/$")


def delete_prefix(prefix: str) -> int:
    import os

    prefix = prefix.strip().strip("/") + "/"
    if not PREFIX_RE.match(prefix):
        raise ValueError("Prefix must contain only lowercase letters, numbers, hyphens, and one trailing slash.")

    bucket = os.environ["R2_BUCKET"]
    client = r2_client()
    deleted = 0
    continuation_token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        response = client.list_objects_v2(**kwargs)
        objects = [{"Key": item["Key"]} for item in response.get("Contents", [])]
        if objects:
            client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
            deleted += len(objects)
        continuation_token = response.get("NextContinuationToken")
        if not continuation_token:
            break

    print(f"Deleted {deleted} object(s) from r2://{bucket}/{prefix}")
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True, help="R2 prefix to delete, for example old-show")
    args = parser.parse_args()
    delete_prefix(args.prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
