import os
from io import BytesIO

import boto3
import requests

s3 = boto3.client(
    service_name="s3",
    endpoint_url=os.getenv("S3_URL_ALTERNATIVE"),
    aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
    region_name="eeur",  # Must be one of: wnam, enam, weur, eeur, apac, auto
)

bucket = os.getenv("S3_BUCKET_NAME")

url = "https://media.aision.io/images/d46bf15e-178f-4760-8deb-9434ab18865f.webp"
r = requests.get(url)
r.raise_for_status()

image = BytesIO(r.content)
image.seek(0)
s3.upload_fileobj(image, Bucket=bucket, Key="123.webp")
