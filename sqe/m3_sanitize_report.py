"""Mask synthetic credentials in a Playwright HTML report before it is committed as evidence.

Playwright records fill() values and request options in the step log that is embedded (as a base64 zip)
inside index.html, so the test accounts' passwords and API tokens would otherwise be published.
Every fixture secret is replaced by '***' in the embedded zip and in the report's data files; the report
keeps working. The script exits non-zero if any secret is still present afterwards.

Usage: python sqe/m3_sanitize_report.py <path to playwright-report directory>
"""
import base64
import io
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'local' / 'sqe' / 'windows' / 'fixtures.json'
MASK = '***'


def secrets():
    config = json.loads(FIXTURES.read_text(encoding='utf-8'))
    values = [config['roles'][role][key] for role in config['roles'] for key in ('token', 'password')]
    return sorted({v for v in values if v}, key=len, reverse=True)


def mask_text(text, values):
    for value in values:
        text = text.replace(value, MASK)
    return text


def mask_zip(raw, values):
    source = zipfile.ZipFile(io.BytesIO(raw))
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            try:
                data = mask_text(data.decode('utf-8'), values).encode('utf-8')
            except UnicodeDecodeError:
                pass  # binary entries (screenshots) cannot contain the text secrets
            target.writestr(item, data)
    return out.getvalue()


def contains_secret(report, values):
    html = (report / 'index.html').read_text(encoding='utf-8')
    texts = [html]
    for blob in re.findall(r'data:application/zip;base64,([A-Za-z0-9+/=]+)', html):
        z = zipfile.ZipFile(io.BytesIO(base64.b64decode(blob)))
        texts += [z.read(n).decode('utf-8', 'ignore') for n in z.namelist()]
    for path in report.rglob('*'):
        if path.is_file() and path.name != 'index.html':
            raw = path.read_bytes()
            if raw[:2] == b'PK':
                z = zipfile.ZipFile(io.BytesIO(raw))
                texts += [z.read(n).decode('utf-8', 'ignore') for n in z.namelist()]
            else:
                texts.append(raw.decode('utf-8', 'ignore'))
    return any(v in t for v in values for t in texts)


def main(report):
    values = secrets()
    index = report / 'index.html'
    html = index.read_text(encoding='utf-8')

    def replace(match):
        return 'data:application/zip;base64,' + base64.b64encode(
            mask_zip(base64.b64decode(match.group(1)), values)).decode('ascii')

    html = re.sub(r'data:application/zip;base64,([A-Za-z0-9+/=]+)', replace, html)
    index.write_text(mask_text(html, values), encoding='utf-8')

    for path in report.rglob('*'):
        if path.is_file() and path != index:
            raw = path.read_bytes()
            if raw[:2] == b'PK':
                path.write_bytes(mask_zip(raw, values))
            else:
                try:
                    path.write_text(mask_text(raw.decode('utf-8'), values), encoding='utf-8')
                except UnicodeDecodeError:
                    pass

    if contains_secret(report, values):
        print('Secrets are still present in the report.', file=sys.stderr)
        return 1
    print(f'Sanitized {report}: {len(values)} secrets masked, none remaining.')
    return 0


if __name__ == '__main__':
    sys.exit(main(Path(sys.argv[1])))
