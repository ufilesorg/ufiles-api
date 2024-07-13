import os
from io import BytesIO

import boto3
import requests

s3 = boto3.client(
    service_name="s3",
    endpoint_url=os.getenv("S3_ENDPOINT"),
    aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
    region_name=os.getenv("S3_REGION"),  # Must be one of: wnam, enam, weur, eeur, apac, auto
)

bucket = os.getenv("S3_BUCKET_NAME")


def list_all_files(bucket_name):
    """List all files in the specified S3 bucket."""
    try:
        response = s3.list_objects_v2(Bucket=bucket_name)
        if "Contents" in response:
            return [obj["Key"] for obj in response["Contents"]]
        else:
            return []
    except Exception as e:
        print(f"Error occurred while listing objects: {e}")
        return []


def delete_all_files(bucket_name):
    """Delete all files in the specified S3 bucket."""
    try:
        keys_to_delete = list_all_files(bucket_name)
        if not keys_to_delete:
            print(f"No objects found in bucket {bucket_name} to delete.")
            return

        delete_requests = [{"Key": key} for key in keys_to_delete]

        response = s3.delete_objects(
            Bucket=bucket_name, Delete={"Objects": delete_requests, "Quiet": True}
        )

        if "Errors" in response:
            print(
                f"Failed to delete some objects in the bucket {bucket_name} : {response['Errors']}"
            )
        else:
            print(f"All objects in bucket {bucket_name} successfully deleted.")

    except Exception as e:
        print(f"Error occurred while deleting objects: {e}")


# Call the function to delete all files
delete_all_files(bucket)

url = "https://media.aision.io/images/d46bf15e-178f-4760-8deb-9434ab18865f.webp"
r = requests.get(url)
r.raise_for_status()

image = BytesIO(r.content)
image.seek(0)
s3.upload_fileobj(image, Bucket=bucket, Key="123.webp")
