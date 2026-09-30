"""Exercise flat-install update decisions with isolated command stand-ins."""
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'update-direct-panel.sh'


def prepare(tmp_path):
    if os.geteuid() != 0:
        pytest.skip('installer requires root; fixture never modifies host services')
    installed = tmp_path / 'flat-server'
    installed.mkdir()
    (installed / 'app').mkdir()
    (installed / 'app/main.py').write_text('old application')
    (installed / '.env').write_text('FGRCK_JWT_SECRET=fixture-secret\nPOSTGRES_PASSWORD=fixture-db\n')
    (installed / 'docker-compose.yml').write_text('services:\n  api:\n    build: .\n')
    (installed / 'Caddyfile').write_text('preserved HTTPS configuration')
    (installed / 'Dockerfile').write_text('old image')
    (installed / 'requirements.txt').write_text('old requirements')
    source = tmp_path / 'source/server'
    (source / 'app').mkdir(parents=True)
    (source / 'app/main.py').write_text('new application')
    (source / 'app/direct_mttl.py').write_text('new IPC adapter')
    (source / 'Dockerfile').write_text('new image')
    (source / 'requirements.txt').write_text('new requirements')
    (source / 'install-direct-mttl-lab.sh').write_text('#!/bin/bash\nexit 0\n')
    commands = tmp_path / 'bin'
    commands.mkdir()
    standins = {
        'git': '#!/bin/bash\n[[ "$1" == clone ]] || exit 9\ncp -a "$FIXTURE_SOURCE" "${@: -1}"\n',
        'docker': '#!/bin/bash\nprintf "%s\\n" "$*" >> "$FIXTURE_DOCKER_LOG"\nif [[ "$*" == "compose config --services" ]]; then printf "db\\napi\\ncaddy\\n"; fi\nif [[ "$*" == "compose exec -T api python -" ]]; then cat >/dev/null; fi\n',
        'getent': '#!/bin/bash\nprintf "fgrck-mttl-ipc:x:19087:\\n"\n',
        'systemctl': '#!/bin/bash\nexit 0\n',
    }
    for name, text in standins.items():
        path = commands / name
        path.write_text(text)
        path.chmod(0o755)
    env = {**os.environ, 'PATH': str(commands) + ':' + os.environ['PATH'],
           'FGRCK_INSTALL_DIR': str(installed),
           'NEXVARY_MTTL_ENV_FILE': str(tmp_path / 'lab.env'),
           'FIXTURE_SOURCE': str(source.parent),
           'FIXTURE_DOCKER_LOG': str(tmp_path / 'docker.log')}
    return installed, env


def test_flat_update_preserves_config_and_is_repeatable(tmp_path):
    installed, env = prepare(tmp_path)
    original_compose = (installed / 'docker-compose.yml').read_bytes()
    original_env = (installed / '.env').read_bytes()
    for _ in range(2):
        result = subprocess.run(['bash', str(SCRIPT)], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
    assert not (installed / '.git').exists()
    assert (installed / 'app/main.py').read_text() == 'new application'
    assert (installed / 'app/direct_mttl.py').exists()
    assert (installed / 'docker-compose.yml').read_bytes() == original_compose
    assert (installed / 'Caddyfile').read_text() == 'preserved HTTPS configuration'
    assert 'FGRCK_JWT_SECRET=fixture-secret' in (installed / '.env').read_text()
    assert 'POSTGRES_PASSWORD=fixture-db' in (installed / '.env').read_text()
    assert (installed / '.env').read_text().count('FGRCK_DIRECT_MTTL_MACS=') == 1
    backups = list(installed.glob('direct-backup-*'))
    assert len(backups) == 2
    assert any((backup / '.env').read_bytes() == original_env for backup in backups)
    override = (installed / 'docker-compose.override.yml').read_text()
    assert '/run/nexvary-direct-mttl' in override
    assert '19087' in override
    calls = Path(env['FIXTURE_DOCKER_LOG']).read_text()
    assert 'compose up -d --build --no-deps api' in calls
    assert ' down' not in calls


def test_custom_override_stops_before_changes(tmp_path):
    installed, env = prepare(tmp_path)
    (installed / 'docker-compose.override.yml').write_text('# existing custom configuration\n')
    result = subprocess.run(['bash', str(SCRIPT)], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'custom Compose override' in result.stderr
    assert (installed / 'app/main.py').read_text() == 'old application'
    assert 'FGRCK_DIRECT_MTTL_MACS' not in (installed / '.env').read_text()
