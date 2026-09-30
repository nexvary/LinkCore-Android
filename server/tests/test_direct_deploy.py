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


def test_legacy_extension_preserves_runtime_and_installs_once(tmp_path):
    installed, env = prepare(tmp_path)
    installed_main = 'from .database import Base, SessionLocal, engine\nFG_LINK_PANEL_TOKEN = "fixture"\ndef get_db(): pass\ndef _panel_guard(): pass\ndef _log(): pass\napp = None\n'
    (installed / 'app/main.py').write_text(installed_main)
    (installed / 'app/database.py').write_text('# Original SQLite configuration\n')
    source = Path(env['FIXTURE_SOURCE']) / 'server'
    for module in ('direct_mttl.py', 'legacy_direct.py', 'legacy_direct_ui.py', 'legacy_direct_users.py', 'legacy_direct_users_ui.py'):
        (source / 'app' / module).write_text('# New extension module\n')
    (source / 'direct_mttl_lab.py').write_text('# New daemon\n')
    lab = tmp_path / 'lab/server'
    lab.mkdir(parents=True)
    (lab / 'direct_mttl_lab.py').write_text('# Previous daemon\n')
    env['NEXVARY_MTTL_INSTALL_DIR'] = str(lab.parent)
    env['NEXVARY_MTTL_SYSTEMD_DROPIN_DIR'] = str(tmp_path / 'systemd')
    installer = SCRIPT.parent / 'install-legacy-direct-extension.sh'
    original_dockerfile = (installed / 'Dockerfile').read_bytes()
    original_requirements = (installed / 'requirements.txt').read_bytes()
    original_compose = (installed / 'docker-compose.yml').read_bytes()
    for _ in range(2):
        result = subprocess.run(['bash', str(installer)], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
    assert (installed / 'Dockerfile').read_bytes() == original_dockerfile
    assert (installed / 'requirements.txt').read_bytes() == original_requirements
    assert (installed / 'docker-compose.yml').read_bytes() == original_compose
    assert (installed / 'app/database.py').read_text() == '# Original SQLite configuration\n'
    new_main = (installed / 'app/main.py').read_text()
    assert new_main.startswith(installed_main)
    assert new_main.count('# FG_DIRECT_EXTENSION_V1') == 1
    assert 'FGRCK_JWT_SECRET=fixture-secret' in (installed / '.env').read_text()
    assert len(list(installed.glob('direct-extension-backup-*'))) == 2


def test_replacement_updater_rejects_legacy_runtime(tmp_path):
    installed, env = prepare(tmp_path)
    (installed / 'app/main.py').write_text('from .database import Base\nFG_LINK_PANEL_TOKEN = "fixture"\n')
    result = subprocess.run(['bash', str(SCRIPT)], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'install-legacy-direct-extension.sh' in result.stderr
    assert not list(installed.glob('direct-backup-*'))


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_customer_update_preserves_flat_runtime_and_rolls_back(tmp_path, backend):
    import sqlite3
    installed, env = prepare(tmp_path)
    original_main = '# FG_DIRECT_EXTENSION_V1\n# Original API and database remain intact\n'
    (installed / 'app/main.py').write_text(original_main)
    (installed / 'app/database.py').write_text('# Existing database configuration\n')
    source = Path(env['FIXTURE_SOURCE']) / 'server'
    modules = ('direct_mttl.py', 'legacy_direct.py', 'legacy_direct_ui.py', 'legacy_direct_users.py', 'legacy_direct_users_ui.py')
    for module in modules:
        (source / 'app' / module).write_text('# Valid new module\n')
    (source / 'direct_mttl_lab.py').write_text('# Valid new daemon\n')
    lab = tmp_path / 'lab/server'
    lab.mkdir(parents=True)
    (lab / 'direct_mttl_lab.py').write_text('# Previous daemon\n')
    database = tmp_path / 'original.sqlite'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE existing_accounts (id INTEGER PRIMARY KEY, name TEXT)')
        db.execute("INSERT INTO existing_accounts(name) VALUES ('existing-customer')")
    commands = tmp_path / 'bin'
    curl = commands / 'curl'
    curl.write_text('''#!/bin/bash
while [[ $# -gt 0 ]]; do
 case "$1" in
  -o) output="$2"; shift 2;;
  https://*) url="$1"; shift;;
  *) shift;;
 esac
done
name="${url##*/}"
if [[ "$url" == */app/* ]]; then cp "$FIXTURE_SOURCE/server/app/$name" "$output"; else cp "$FIXTURE_SOURCE/server/$name" "$output"; fi
''')
    curl.chmod(0o755)
    docker = commands / 'docker'
    docker.write_text('''#!/bin/bash
printf "%s\\n" "$*" >> "$FIXTURE_DOCKER_LOG"
if [[ "$*" == "compose exec -T api python -c "* ]]; then printf '%s\\n' "$FIXTURE_BACKEND"; fi
if [[ "$*" == "compose exec -T api python -" ]]; then
 script=$(cat)
 if [[ "$script" == *"url = engine.url"* ]]; then printf 'fguser\\nfgdatabase\\n'; fi
fi
if [[ "$*" == "compose exec -T db sh "* ]]; then
 [[ -z "${FIXTURE_DUMP_FAIL:-}" ]] || exit 3
 printf 'fixture-custom-pg-dump'
fi
if [[ "$*" == "compose exec -T db pg_restore --list" ]]; then cat >/dev/null; printf 'validated archive\\n'; fi
if [[ "$*" == compose\ cp\ * ]]; then cp "$FIXTURE_DATABASE" "${@: -1}"; fi
if [[ "$*" == "compose up -d --build --no-deps api" && -n "${FIXTURE_FAIL_FLAG:-}" && ! -f "$FIXTURE_FAIL_FLAG" ]]; then touch "$FIXTURE_FAIL_FLAG"; exit 2; fi
''')
    docker.chmod(0o755)
    env.update(NEXVARY_MTTL_INSTALL_DIR=str(lab.parent),
               NEXVARY_MTTL_SYSTEMD_DROPIN_DIR=str(tmp_path / 'systemd'),
               FG_DIRECT_SOURCE_COMMIT='1' * 40, FIXTURE_DATABASE=str(database), FIXTURE_BACKEND=backend)
    preserved = {name: (installed / name).read_bytes() for name in
                 ('app/main.py', 'app/database.py', '.env', 'Dockerfile', 'requirements.txt', 'docker-compose.yml', 'Caddyfile')}
    installer = SCRIPT.parent / 'update-direct-users.sh'
    result = subprocess.run(['bash', str(installer)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    for name, content in preserved.items():
        assert (installed / name).read_bytes() == content
    assert 'StateDirectory=nexvary-direct-mttl' in (tmp_path / 'systemd/direct-users.conf').read_text()
    assert (lab / 'direct_mttl_lab.py').read_text() == '# Valid new daemon\n'
    (source / 'app/legacy_direct_users.py').write_text('# Replacement that will roll back\n')
    env['FIXTURE_FAIL_FLAG'] = str(tmp_path / 'failed-once')
    previous = (installed / 'app/legacy_direct_users.py').read_bytes()
    result = subprocess.run(['bash', str(installer)], env=env, capture_output=True, text=True)
    assert result.returncode != 0 and 'previous code restored' in result.stderr
    assert (installed / 'app/legacy_direct_users.py').read_bytes() == previous
    for name, content in preserved.items():
        assert (installed / name).read_bytes() == content
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT name FROM existing_accounts').fetchall() == [('existing-customer',)]
    backups = list(installed.glob('direct-users-backup-*'))
    assert len(backups) == 2
    backup_name = 'database.sqlite' if backend == 'sqlite' else 'database.pgdump'
    assert all((path / backup_name).exists() for path in backups)
    if backend == 'postgresql':
        calls = Path(env['FIXTURE_DOCKER_LOG']).read_text()
        assert 'pg_restore --list' in calls and 'fguser fgdatabase' in calls
        env['FIXTURE_DUMP_FAIL'] = '1'
        previous_daemon = (lab / 'direct_mttl_lab.py').read_bytes()
        result = subprocess.run(['bash', str(installer)], env=env, capture_output=True, text=True)
        assert result.returncode != 0
        assert (installed / 'app/legacy_direct_users.py').read_bytes() == previous
        assert (lab / 'direct_mttl_lab.py').read_bytes() == previous_daemon
