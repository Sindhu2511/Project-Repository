import os

import boto3
from dotenv import load_dotenv

load_dotenv()
s3 = boto3.client("s3", region_name=os.environ["AWS_REGION"])
resp = s3.list_objects_v2(Bucket=os.environ["S3_BUCKET"])
print("Connected. Files in bucket:", resp.get("KeyCount", 0))