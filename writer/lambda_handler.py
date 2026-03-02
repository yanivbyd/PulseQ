import json
import os
import tempfile
from pathlib import Path

import boto3

# In Lambda the bundle root contains writer.py as a sibling module.
# In tests writer/ is a package, so fall back to the submodule import.
try:
    from writer import run  # Lambda environment: writer.py at bundle root
except ImportError:
    from writer.writer import run  # type: ignore[no-redef]  # Test environment

# Module-level cache for the OpenAI API key (populated on cold start)
_api_key: str | None = None


def _get_api_key() -> str:
    global _api_key
    if _api_key is None:
        client = boto3.client("secretsmanager", region_name="eu-west-1")
        response = client.get_secret_value(SecretId=os.environ["SECRET_NAME"])
        _api_key = response["SecretString"]
    return _api_key


def _download_inputs(s3_client, bucket: str, tmp_inputs: Path) -> None:
    for key in ("instructions.md", "topic.md", "history.md"):
        s3_client.download_file(bucket, f"inputs/{key}", str(tmp_inputs / key))


def handler(event, context):
    input_bucket = os.environ["INPUT_BUCKET"]
    output_bucket = os.environ["OUTPUT_BUCKET"]

    try:
        api_key = _get_api_key()
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": f"Failed to retrieve secret: {e}"})}

    os.environ["OPENAI_API_KEY"] = api_key

    s3 = boto3.client("s3", region_name="eu-west-1")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tmp_inputs = tmp_path / "inputs"
        tmp_inputs.mkdir()
        tmp_docs = tmp_path / "docs"

        try:
            _download_inputs(s3, input_bucket, tmp_inputs)
        except Exception as e:
            return {"statusCode": 500, "body": json.dumps({"error": f"Failed to download inputs: {e}"})}

        try:
            run(base_dir=tmp_path, docs_dir=tmp_docs)
        except Exception as e:
            return {"statusCode": 500, "body": json.dumps({"error": f"writer.run() failed: {e}"})}

        html_files = list(tmp_docs.glob("*.html"))
        if not html_files:
            return {"statusCode": 500, "body": json.dumps({"error": "No HTML output produced"})}

        output_file = html_files[0]
        key = output_file.name

        try:
            s3.upload_file(
                str(output_file),
                output_bucket,
                key,
                ExtraArgs={"ContentType": "text/html"},
            )
        except Exception as e:
            return {"statusCode": 500, "body": json.dumps({"error": f"Failed to upload output: {e}"})}

    url = f"http://{output_bucket}.s3-website.eu-west-1.amazonaws.com/{key}"
    return {"statusCode": 200, "body": json.dumps({"url": url})}
