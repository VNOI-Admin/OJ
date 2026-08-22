import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def release_key(code, version):
    return f'releases/{code}/{version}'


def build_release(source_dir, code, version):
    """Build a deterministic zip and manifest for a local problem directory."""
    source_dir = Path(source_dir).resolve()
    if not source_dir.is_dir():
        raise ValueError(f'Problem directory does not exist: {source_dir}')

    with tempfile.TemporaryDirectory() as temp_dir:
        package_path = Path(temp_dir) / 'package.zip'
        with zipfile.ZipFile(package_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(source_dir.rglob('*')):
                if path.is_file():
                    archive.write(path, path.relative_to(source_dir).as_posix())

        digest = hashlib.sha256(package_path.read_bytes()).hexdigest()
        manifest = {
            'code': code,
            'version': version,
            'sha256': digest,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'package': f'{release_key(code, version)}/package.zip',
        }
        return package_path.read_bytes(), json.dumps(manifest, sort_keys=True).encode(), manifest


def verify_sha256(path, expected):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest() == expected


def activate_release(package_path, target_dir, code):
    """Extract a verified package and atomically replace the active problem."""
    target_dir = Path(target_dir)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=f'.{code}.', dir=target_dir.parent))
    try:
        with zipfile.ZipFile(package_path) as archive:
            staging_root = staging_dir.resolve()
            for member in archive.infolist():
                destination = (staging_root / member.filename).resolve()
                if os.path.commonpath((staging_root, destination)) != str(staging_root):
                    raise ValueError(f'Unsafe path in release package: {member.filename}')
            archive.extractall(staging_dir)
        active_dir = target_dir.parent / f'.{code}.active'
        previous_dir = target_dir.parent / f'.{code}.previous'
        if active_dir.exists():
            shutil.rmtree(active_dir)
        staging_dir.rename(active_dir)
        if target_dir.exists():
            if previous_dir.exists():
                shutil.rmtree(previous_dir)
            target_dir.rename(previous_dir)
        active_dir.rename(target_dir)
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
