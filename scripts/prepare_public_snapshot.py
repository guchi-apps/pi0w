#!/usr/bin/env python3
"""Create a sanitized, single-commit checkout without publishing or touching source history."""
import argparse
import io
import re
from pathlib import Path
import struct
import subprocess
import tarfile
import zlib

# PNG metadata is unnecessary for application icons.
PNG_CHUNKS = {b'IHDR', b'PLTE', b'IDAT', b'IEND', b'tRNS', b'gAMA', b'cHRM', b'sRGB', b'sBIT', b'pHYs'}
LEGACY_REPOSITORY = 'pi0w_' + '260719'
PRIVATE_VPS = 'm-' + 'guchi/vps'

def public_text(text, repository):
    """Retarget the exported copy; private source and live configuration stay unchanged."""
    text = text.replace('guchi-apps/' + LEGACY_REPOSITORY, repository)
    text = text.replace(LEGACY_REPOSITORY, repository.split('/')[1])
    text = text.replace('[' + PRIVATE_VPS + '](https://github.com/' + PRIVATE_VPS + ')', 'VPS側の管理リポジトリ')
    text = text.replace(PRIVATE_VPS, 'VPS側')
    return text

def audit_text(text, path):
    # Fail closed on known private identifiers and recognizable credentials.
    patterns = (r'guc' + r'chii\.com', LEGACY_REPOSITORY, PRIVATE_VPS,
                r'192\.168\.' + r'2\.\d+', 'B0:E9:FE:' + 'B3:5F:B5',
                r'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----',
                r'\bgh[pousr]_[A-Za-z0-9]{20,}', r'\bgithub_pat_[A-Za-z0-9_]{20,}',
                r'\bAKIA[A-Z0-9]{16}\b')
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns):
        raise ValueError('Public export audit failed: ' + path)

def clean_png(data):
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Invalid PNG')
    output = bytearray(data[:8])
    offset = 8
    ended = False
    while offset < len(data):
        length = struct.unpack('>I', data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(data):
            raise ValueError('Truncated PNG')
        payload = data[offset + 8:offset + 8 + length]
        crc = struct.unpack('>I', data[end - 4:end])[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise ValueError('PNG checksum mismatch')
        if kind in PNG_CHUNKS:
            output.extend(data[offset:end])
        elif kind[:1].isupper():
            raise ValueError('Unknown critical PNG chunk')
        offset = end
        if kind == b'IEND':
            ended = True
            break
    if not ended:
        raise ValueError('Missing PNG end')
    return bytes(output)

def prepare(source, destination, repository='guchi-apps/pi0w'):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or LEGACY_REPOSITORY in repository:
        raise ValueError('Invalid public repository')
    if destination.exists():
        raise ValueError('Destination must not exist')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=str(source)).strip():
        raise ValueError('Commit and review source changes first')
    archive = subprocess.check_output(['git', 'archive', 'HEAD'], cwd=str(source))
    destination.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts or not member.isfile():
                if member.isdir():
                    continue
                raise ValueError('Unsafe archive entry: ' + member.name)
            # Only offline CI is enabled initially; shared agent/release callers need a public-input audit.
            if member.name.startswith('.github/workflows/') and path.name != 'ci.yml':
                continue
            if member.name in ('docs/publication-review.md', 'docs/issuedeck.md', 'AGENTS.md', 'CLAUDE.md'):
                continue
            if (path.name.startswith('.env') and path.name != '.env.example') or path.name == 'sensors.json' or path.suffix in ('.pem', '.key', '.db', '.sqlite'):
                raise ValueError('Local configuration was tracked: ' + member.name)
            data = tar.extractfile(member).read()
            if path.suffix.lower() == '.png':
                data = clean_png(data)
            else:
                try:
                    text = public_text(data.decode('utf-8'), repository)
                except UnicodeDecodeError:
                    raise ValueError('Unsupported binary requires public review: ' + member.name)
                audit_text(text, member.name)
                data = text.encode('utf-8')
            target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(member.mode & 0o777)
    readme = destination / 'README.md'
    readme.write_text(readme.read_text().replace('開発: [AGENTS.md](AGENTS.md)、[IssueDeck連携](docs/issuedeck.md)。\n公開移行: [docs/publication-review.md](docs/publication-review.md)。', '公開版はハードウェアなしCIのみを有効にしています。IssueDeck連携は公開入力の権限確認後に導入します。'))
    subprocess.check_call(['git', 'init', '-q', '-b', 'main'], cwd=str(destination))
    subprocess.check_call(['git', 'add', '.'], cwd=str(destination))
    subprocess.check_call(['git', '-c', 'user.name=Public snapshot', '-c', 'user.email=public-snapshot@example.invalid', 'commit', '-qm', 'Initial sanitized source snapshot'], cwd=str(destination))
    if subprocess.check_output(['git', 'rev-list', '--count', 'HEAD'], cwd=str(destination)).strip() != b'1':
        raise ValueError('Unexpected history')
    return destination

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--repository', default='guchi-apps/pi0w')
    args = parser.parse_args()
    print(prepare(Path(__file__).resolve().parents[1], args.destination.resolve(), args.repository))

