"""Exercise the narrow false-positive exception without embedding credentials."""
from pathlib import Path
import secrets
import subprocess
import tempfile

config = Path('.gitleaks.toml').resolve()
with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / 'schema.py'
    field = '_'.join(['default', 'tmdb', 'api', 'key'])
    line = 'vol.Required(TMDB_KEY_FIELD, default=' + field + ' or ""): str,'
    source.write_text(line + '\n')
    args = ['gitleaks', 'dir', directory, '--config', str(config), '--redact=100', '--no-banner']
    result = subprocess.run(args, capture_output=True)
    assert result.returncode == 0, 'Empty schema fallback must not be flagged'
    source.write_text(line.replace('""', '"' + secrets.token_hex(32) + '"') + '\n')
    result = subprocess.run(args, capture_output=True)
    assert result.returncode == 1, 'Inserted credential must still be detected'
print('Exact schema exception and inserted-secret detection verified (values suppressed)')
