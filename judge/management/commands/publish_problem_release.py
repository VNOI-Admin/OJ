import os

import boto3
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from judge.utils.problem_releases import build_release, release_key


class Command(BaseCommand):
    help = 'Publish a local problem directory as a versioned Cloudflare R2 release.'

    def add_arguments(self, parser):
        parser.add_argument('code')
        parser.add_argument('version')

    def handle(self, *args, **options):
        code = options['code']
        version = options['version']
        required = ('R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_ENDPOINT_URL', 'R2_PROBLEMS_BUCKET')
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise CommandError(f'Missing R2 settings: {", ".join(missing)}')

        source_dir = os.path.join(settings.DMOJ_PROBLEM_DATA_ROOT, code)
        package, manifest_bytes, manifest = build_release(source_dir, code, version)
        client = boto3.client(
            's3',
            endpoint_url=os.environ['R2_ENDPOINT_URL'],
            region_name='auto',
            aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
            aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        )
        prefix = release_key(code, version)
        bucket = os.environ['R2_PROBLEMS_BUCKET']
        client.put_object(Bucket=bucket, Key=f'{prefix}/package.zip', Body=package,
                          ContentType='application/zip')
        client.put_object(Bucket=bucket, Key=f'{prefix}/manifest.json', Body=manifest_bytes,
                          ContentType='application/json')
        self.stdout.write(self.style.SUCCESS(
            f'Published {code}@{version} ({manifest["sha256"]})',
        ))
