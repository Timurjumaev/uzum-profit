"""B2.10: staging skriptlari — deploy (zaxira → migratsiya → sog'liq → qaytish), zaxira, sirlar fayli.

``docker`` va ``curl`` soxta (PATH'da): har chaqiruv jurnalga yoziladi, xatolar muhit o'zgaruvchilari bilan
beriladi. Haqiqiy konteynerlar bilan to'liq oqim — CI'dagi ``staging`` ishi.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from upapi.settings import Environment, Settings

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = ["infra/staging/lib.sh", "infra/staging/deploy.sh", "infra/backup/backup.sh"]

FAKE_DOCKER = r"""#!/usr/bin/env bash
echo "UP_TAG=${UP_TAG:-} $*" >> "$FAKE_LOG"
args=" $* "
if [ -n "${FAKE_FAIL:-}" ] && [[ "$args" == *"$FAKE_FAIL"* ]] &&
   [[ -z "${FAKE_FAIL_TAG:-}" || "${UP_TAG:-}" == "$FAKE_FAIL_TAG" ]]; then
  exit 1
fi
case "$args" in
  *" pg_dump "*) printf 'PGDMP-fake' ;;
  *" pg_restore --list "*) cat > /dev/null ;;
  *" ps --status running --services "*) echo api; echo worker; echo caddy ;;
  *" config --images api caddy "*) echo "ghcr.io/x/uzum-profit-api:$UP_TAG"; echo "ghcr.io/x/uzum-profit-web:$UP_TAG"; echo postgres:18 ;;
  *" image inspect "*":missing "*|*" image inspect postgres:18 "*) exit 1 ;;
  *" image ls "*) printf '%s\n' ghcr.io/x/uzum-profit-api:old ghcr.io/x/uzum-profit-api:v1 ghcr.io/x/uzum-profit-web:v2 postgres:18 ;;
esac
exit 0
"""

FAKE_CURL = r"""#!/usr/bin/env bash
echo "curl $*" >> "$FAKE_LOG"
[ -n "${FAKE_CURL_FAIL:-}" ] && exit 22
echo '{"status":"ok","version":"0.0.0","env":"staging"}'
"""


def _exe(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """Serverdagi /srv/uzum-profit ko'rinishi: infra/ nusxasi va .env."""
    root = tmp_path / "srv"
    for script in SCRIPTS:
        (root / script).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / script, root / script)
    (root / ".env").write_text("UP_ENV=staging\nUP_DOMAIN=1-2-3-4.sslip.io\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _exe(bin_dir / "docker", FAKE_DOCKER)
    _exe(bin_dir / "curl", FAKE_CURL)
    return root


def run(root: Path, script: str, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    full_env = {
        **os.environ,
        "PATH": f"{root.parent / 'bin'}:{os.environ['PATH']}",
        "UP_ROOT": str(root),
        "FAKE_LOG": str(root / "calls.log"),
        "UP_HEALTH_TRIES": "2",
        "UP_HEALTH_SLEEP": "0",
        "UP_WORKER_SETTLE": "0",
        **env,
    }
    return subprocess.run(
        [str(root / script), *args], env=full_env, capture_output=True, text=True, timeout=60
    )


def calls(root: Path) -> list[str]:
    return (root / "calls.log").read_text().splitlines()


def index(lines: list[str], needle: str) -> int:
    return next(i for i, line in enumerate(lines) if needle in line)


def test_deploy_order_and_tag(root: Path) -> None:
    (root / ".deployed-tag").write_text("v1\n")
    r = run(root, "infra/staging/deploy.sh", "v2", UP_REGISTRY_TOKEN="ghs_secret")
    assert r.returncode == 0, r.stderr
    log = calls(root)
    # Zaxira → migratsiya → yangi konteynerlar → sog'liq tekshiruvi (06 §2).
    steps = [
        "login ghcr.io",
        "pull --quiet api caddy",
        "up -d --wait postgres",
        "pg_dump",
        "pg_restore --list",
        "run --rm --pull never migrate",
        "up -d --no-build --wait --wait-timeout 180 api worker caddy",
        "curl",
        "ps --status running --services",
        "logout ghcr.io",
    ]
    positions = [index(log, s) for s in steps]
    assert positions == sorted(positions)
    assert all(
        "UP_TAG=v2" in log[i] for i in positions if "compose" in log[i] and "pg_" not in log[i]
    )
    assert (
        "ghs_secret" not in (root / "calls.log").read_text() + r.stderr
    )  # token faqat stdin orqali
    health = log[index(log, "curl")]
    assert "--resolve 1-2-3-4.sslip.io:443:127.0.0.1 https://1-2-3-4.sslip.io/health" in health
    assert " -k " not in health  # serverda sertifikat haqiqiy tekshiriladi
    assert (root / ".deployed-tag").read_text().strip() == "v2"
    # Joriy (v2) va oldingi (v1) image'lar qoladi, qolgani o'chiriladi.
    removed = log[index(log, "image rm")]
    assert "uzum-profit-api:old" in removed and ":v1" not in removed and ":v2" not in removed
    assert len(list((root / "backups").glob("uzum-*-pre-deploy.dump"))) == 1


def test_failed_health_rolls_back(root: Path) -> None:
    (root / ".deployed-tag").write_text("v1\n")
    r = run(root, "infra/staging/deploy.sh", "v2", FAKE_CURL_FAIL="1", UP_SKIP_PULL="1")
    assert r.returncode == 1
    log = calls(root)
    assert not any(" pull " in line for line in log)
    ups = [line for line in log if "up -d --no-build --wait --wait-timeout 180" in line]
    assert [u.split()[0] for u in ups] == ["UP_TAG=v2", "UP_TAG=v1"]
    assert "v1 ham ko'tarilmadi" in r.stderr  # soxta curl v1 da ham yiqiladi
    assert (root / ".deployed-tag").read_text().strip() == "v1"


def test_rollback_succeeds_when_previous_is_healthy(root: Path) -> None:
    (root / ".deployed-tag").write_text("v1\n")
    r = run(
        root,
        "infra/staging/deploy.sh",
        "v2",
        UP_SKIP_PULL="1",
        FAKE_FAIL="api worker caddy",
        FAKE_FAIL_TAG="v2",
    )
    assert r.returncode == 1
    assert "v2 ishlamadi; v1 qaytarildi" in r.stderr
    assert (root / ".deployed-tag").read_text().strip() == "v1"


def test_failed_migration_keeps_running_version(root: Path) -> None:
    (root / ".deployed-tag").write_text("v1\n")
    r = run(
        root,
        "infra/staging/deploy.sh",
        "v2",
        UP_SKIP_PULL="1",
        FAKE_FAIL="run --rm --pull never migrate",
    )
    assert r.returncode == 1 and "migratsiya" in r.stderr
    assert not any("api worker caddy" in line for line in calls(root))
    assert (root / ".deployed-tag").read_text().strip() == "v1"


def test_missing_image_stops_before_anything_changes(root: Path) -> None:
    (root / ".deployed-tag").write_text("v1\n")
    r = run(root, "infra/staging/deploy.sh", "missing", UP_SKIP_PULL="1")
    assert r.returncode == 1 and "image yo'q: ghcr.io/x/uzum-profit-api:missing" in r.stderr
    assert not any(" up " in line or "migrate" in line for line in calls(root))


def test_first_deploy_without_previous(root: Path) -> None:
    r = run(root, "infra/staging/deploy.sh", "v1", UP_SKIP_PULL="1", FAKE_CURL_FAIL="1")
    assert r.returncode == 1 and "qaytadigan oldingi versiya yo'q" in r.stderr
    assert not (root / ".deployed-tag").exists()


def test_backup_verifies_and_rotates(root: Path) -> None:
    backups = root / "backups"
    backups.mkdir()
    old, fresh = backups / "uzum-20200101T000000Z-nightly.dump", backups / "uzum-recent.dump"
    for f in (old, fresh):
        f.write_text("x")
    os.utime(old, (0, 0))
    r = run(root, "infra/backup/backup.sh", "nightly")
    assert r.returncode == 0, r.stderr
    made = sorted(p.name for p in backups.iterdir())
    assert old.name not in made and fresh.name in made
    new = [p for p in backups.glob("uzum-2*-nightly.dump")]
    assert len(new) == 1 and new[0].read_text() == "PGDMP-fake"
    assert stat.S_IMODE(new[0].stat().st_mode) == 0o600
    # Tag hali yo'q — compose baribir ishlaydi (UP_TAG=none).
    assert calls(root)[0].startswith("UP_TAG=none ")


def test_backup_rejects_unreadable_dump(root: Path) -> None:
    r = run(root, "infra/backup/backup.sh", "nightly", FAKE_FAIL="pg_restore --list")
    assert r.returncode == 1 and "o'qilmadi" in r.stderr
    assert list((root / "backups").iterdir()) == []  # yarim fayl qolmaydi


def test_backup_label_is_safe(root: Path) -> None:
    assert run(root, "infra/backup/backup.sh", "../x").returncode == 1


def test_gen_env_satisfies_staging_checks(tmp_path: Path) -> None:
    """Yaratilgan ``.env`` bilan ilova staging'ning qat'iy tekshiruvlaridan o'tadi (``Settings.problems``)."""
    env = {**os.environ, "UP_ROOT": str(tmp_path), "UP_TELEGRAM_GATEWAY_TOKEN": "gw-token"}
    script = REPO / "infra/staging/gen-env.sh"
    r = subprocess.run([script, "1-2-3-4.sslip.io"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    path = tmp_path / ".env"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    text = path.read_text()
    assert "gw-token" not in r.stdout + r.stderr
    values = dict(
        line.split("=", 1) for line in text.splitlines() if line and not line.startswith("#")
    )
    assert values["UP_ENV"] == "staging" and values["UP_DOMAIN"] == "1-2-3-4.sslip.io"
    assert values["POSTGRES_PASSWORD"] != values["UP_APP_DB_PASSWORD"]
    assert values["UP_DATABASE_URL"].startswith(
        f"postgresql://up_app:{values['UP_APP_DB_PASSWORD']}@"
    )
    settings = Settings(_env_file=path)  # type: ignore[call-arg]
    assert settings.env is Environment.STAGING
    assert settings.problems() == []
    assert settings.allowed_origins == ["https://1-2-3-4.sslip.io"]
    # Ikkinchi marta — mavjud sirlar ustiga yozilmaydi.
    again = subprocess.run([script, "x.sslip.io"], env=env, capture_output=True, text=True)
    assert again.returncode == 1 and path.read_text() == text
