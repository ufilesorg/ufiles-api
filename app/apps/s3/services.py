import hashlib
import hmac
import logging
import os

from fastapi import Request

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "EBU01VYUFJNH5D5AGO5TV1RJVXM3X4DV")
AWS_SECRET_ACCESS_KEY = os.getenv(
    "AWS_SECRET_ACCESS_KEY",
    "LCL0JkWr1pKrN6xUgX4qUZKR727ddVYQk7WvzCYBxml1hhUvZ7KJ66SnYLr09UmQ",
)
AWS_REGION = os.getenv("AWS_REGION", "cf")
SERVICE = "s3"
ALGORITHM = "AWS4-HMAC-SHA256"


def sign(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def get_signature_key(key, date_stamp, region_name, service_name):
    k_date = sign(("AWS4" + key).encode("utf-8"), date_stamp)
    k_region = sign(k_date, region_name)
    k_service = sign(k_region, service_name)
    k_signing = sign(k_service, "aws4_request")
    return k_signing


async def verify_signature(request: Request):
    try:
        authorization_header = request.headers.get("Authorization")
        amz_date = request.headers.get("x-amz-date")
        if not authorization_header or not amz_date:
            logging.error("Missing authorization or x-amz-date header")
            return False

        logging.info(f"Authorization Header: {authorization_header}")
        logging.info(f"x-amz-date: {amz_date}")

        auth_parts = authorization_header.split(", ")
        credential_part = auth_parts[0]
        signed_headers_part = auth_parts[1]
        signature_part = auth_parts[2]

        credential_scope = credential_part.split(" ")[1].split("/")[1:-1]
        credential_scope = "/".join(credential_scope)

        signed_headers = signed_headers_part.split("SignedHeaders=")[-1].split(";")
        provided_signature = signature_part.split("Signature=")[-1]

        logging.info(f"Signed Headers: {signed_headers}")
        logging.info(f"Credential Scope: {credential_scope}")

        headers_dict = {k.lower(): v for k, v in request.headers.items()}
        sorted_headers = {
            k: headers_dict[k] for k in sorted(headers_dict) if k in signed_headers
        }

        logging.info(f"Headers Dict: {headers_dict}")
        logging.info(f"Sorted Headers: {sorted_headers}")

        canonical_uri = request.url.path
        canonical_querystring = request.url.query
        # canonical_headers = "".join([f"{k}:{v}\n" for k, v in sorted_headers.items()])
        canonical_headers = "".join(
            f"{k.lower()}:{v.strip()}\n" for k, v in request.headers.items()
        )
        payload_hash = hashlib.sha256(await request.body()).hexdigest()
        if headers_dict.get("x-amz-content-sha256") == "UNSIGNED-PAYLOAD":
            payload_hash = (
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            )
        canonical_request = f"{request.method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{';'.join(signed_headers)}\n{payload_hash}"

        logging.info(f"Canonical Request: {canonical_request}")

        string_to_sign = f'{ALGORITHM}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()}'

        logging.info(f"String to Sign: {string_to_sign}")

        date_stamp = credential_scope.split("/")[0]
        signing_key = get_signature_key(
            AWS_SECRET_ACCESS_KEY,
            date_stamp,
            AWS_REGION,
            SERVICE,
        )

        signature = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        logging.info(f"Calculated Signature: {signature}")
        logging.info(f"Provided Signature: {provided_signature}")

        is_valid = provided_signature == signature
        if not is_valid:
            logging.error("Signatures do not match")

        return is_valid
    except Exception as e:
        logging.error(f"Verification failed: {e}")
        return False


def test():
    import boto3
    from io import BytesIO

    session = boto3.Session(
        AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, region_name=AWS_REGION
    )
    client = session.client(
        "s3", endpoint_url="https://stg.ufiles.org/s3", region_name=AWS_REGION
    )

    f = BytesIO(b"salam\n")
    f.seek(0)
    client.put_object(Bucket="mybucket", Key="myfile.txt", Body=f)

