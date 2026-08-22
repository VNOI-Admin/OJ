#!/usr/bin/env python3
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import boto3

# Allow direct execution from a source checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from judge.utils.problem_releases import activate_release, release_key, verify_sha256  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description='Download and atomically activate an R2 problem release.')
    parser.add_argument('code')
    parser.add_argument('version')
    parser.add_argument('--problems-root', default=os.environ.get('PROBLEMS_ROOT', '/problems'))
    args = parser.parse_args()

    client = boto3.client(
        's3', endpoint_url=os.environ['R2_ENDPOINT_URL'], region_name='auto',
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
    )
    bucket = os.environ['R2_PROBLEMS_BUCKET']
    prefix = release_key(args.code, args.version)
    manifest = json.loads(client.get_object(Bucket=bucket, Key=f'{prefix}/manifest.json')['Body'].read())
    if manifest['code'] != args.code or manifest['version'] != args.version:
        raise RuntimeError('Release manifest does not match requested release')

    with tempfile.TemporaryDirectory() as temp_dir:
        package_path = Path(temp_dir) / 'package.zip'
        with package_path.open('wb') as package:
            response = client.get_object(Bucket=bucket, Key=f'{prefix}/package.zip')
            for chunk in iter(lambda: response['Body'].read(1024 * 1024), b''):
                package.write(chunk)
        if not verify_sha256(package_path, manifest['sha256']):
            raise RuntimeError('Release SHA-256 does not match manifest; refusing activation')
        activate_release(package_path, Path(args.problems_root) / args.code, args.code)

    print(f'Activated {args.code}@{args.version} ({manifest["sha256"]})')


if __name__ == '__main__':
    main()
