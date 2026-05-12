#!/usr/bin/env python3
"""
Modular lab installer for:
  - DVWA
  - Metatron
  - OpenClaw

Supports:
  - RHEL/Fedora/Rocky/Alma via dnf
  - Debian/Ubuntu/Kali via apt-get

Usage:
  sudo python3 lab_installer.py --dvwa
  sudo python3 lab_installer.py --openclaw
  sudo python3 lab_installer.py --metatron --metatron-repo https://github.com/OWNER/REPO.git
  sudo python3 lab_installer.py --all --metatron-repo https://github.com/OWNER/REPO.git
"""

import argparse
import os
import secrets
import shutil
import subprocess
from pathlib import Path


WEB_ROOT = Path("/var/www/html")
OPT_ROOT = Path("/opt/lab-tools")

DVWA_REPO = "https://github.com/digininja/DVWA.git"

OPENCLAW_DIR = OPT_ROOT / "openclaw"
OPENCLAW_REPO = "https://github.com/openclaw/openclaw.git"

METATRON_DIR = OPT_ROOT / "metatron"

PKG_MANAGER = None


def run(cmd, cwd=None, check=True):
    print(f"\n[+] Running: {' '.join(str(x) for x in cmd)}")
    subprocess.run(cmd, cwd=cwd, check=check)


def require_root():
    if os.geteuid() != 0:
        raise SystemExit("Run this script with sudo/root.")


def command_exists(cmd):
    return shutil.which(cmd) is not None


def detect_package_manager():
    global PKG_MANAGER

    if PKG_MANAGER:
        return PKG_MANAGER

    if command_exists("dnf"):
        PKG_MANAGER = "dnf"
    elif command_exists("apt-get"):
        PKG_MANAGER = "apt"
    else:
        raise SystemExit("Unsupported system: neither dnf nor apt-get was found.")

    return PKG_MANAGER


def pkg_install(packages):
    pm = detect_package_manager()

    if pm == "dnf":
        run(["dnf", "install", "-y", *packages])

    elif pm == "apt":
        run(["apt-get", "update"])
        run(["apt-get", "install", "-y", *packages])


def enable_service(service):
    run(["systemctl", "enable", "--now", service])


def clone_or_update(repo_url, dest):
    dest = Path(dest)

    if dest.exists() and (dest / ".git").exists():
        run(["git", "pull"], cwd=dest)
    elif dest.exists():
        print(f"[!] {dest} exists but is not a git repo. Skipping clone.")
    else:
        run(["git", "clone", repo_url, str(dest)])


def install_base_packages():
    pm = detect_package_manager()

    if pm == "dnf":
        pkg_install([
            "git",
            "curl",
            "wget",
            "unzip",
            "tar",
            "python3",
            "python3-pip",
            "python3-virtualenv",
        ])
    else:
        pkg_install([
            "git",
            "curl",
            "wget",
            "unzip",
            "tar",
            "python3",
            "python3-pip",
            "python3-venv",
        ])

    OPT_ROOT.mkdir(parents=True, exist_ok=True)


def install_dvwa_packages():
    pm = detect_package_manager()

    if pm == "dnf":
        pkg_install([
            "httpd",
            "mariadb-server",
            "php",
            "php-mysqli",
            "php-gd",
            "php-mbstring",
            "php-xml",
            "php-json",
        ])

        return {
            "web_service": "httpd",
            "db_service": "mariadb",
            "web_user": "apache",
            "web_group": "apache",
            "web_root": WEB_ROOT,
        }

    pkg_install([
        "apache2",
        "mariadb-server",
        "php",
        "php-mysql",
        "php-gd",
        "php-mbstring",
        "php-xml",
        "php-json",
        "libapache2-mod-php",
    ])

    return {
        "web_service": "apache2",
        "db_service": "mariadb",
        "web_user": "www-data",
        "web_group": "www-data",
        "web_root": WEB_ROOT,
    }


def configure_dvwa_php_ini():
    pm = detect_package_manager()

    if pm == "dnf":
        php_ini_candidates = [
            Path("/etc/php.ini"),
        ]
    else:
        php_ini_candidates = list(Path("/etc/php").glob("*/apache2/php.ini"))

    for php_ini in php_ini_candidates:
        if not php_ini.exists():
            continue

        text = php_ini.read_text(errors="ignore")

        replacements = {
            "allow_url_include = Off": "allow_url_include = On",
            "allow_url_fopen = Off": "allow_url_fopen = On",
            "display_errors = Off": "display_errors = On",
        }

        changed = False
        for old, new in replacements.items():
            if old in text:
                text = text.replace(old, new)
                changed = True

        if changed:
            php_ini.write_text(text)
            print(f"[+] Updated PHP config: {php_ini}")


def install_dvwa():
    print("\n========== Installing DVWA ==========")

    cfg = install_dvwa_packages()

    web_service = cfg["web_service"]
    db_service = cfg["db_service"]
    web_user = cfg["web_user"]
    web_group = cfg["web_group"]
    dvwa_dir = cfg["web_root"] / "dvwa"

    enable_service(web_service)
    enable_service(db_service)

    clone_or_update(DVWA_REPO, dvwa_dir)

    config_sample = dvwa_dir / "config" / "config.inc.php.dist"
    config_file = dvwa_dir / "config" / "config.inc.php"

    if config_sample.exists() and not config_file.exists():
        shutil.copy(config_sample, config_file)

    db_password = secrets.token_urlsafe(18)

    sql = f"""
CREATE DATABASE IF NOT EXISTS dvwa;
CREATE USER IF NOT EXISTS 'dvwa'@'localhost' IDENTIFIED BY '{db_password}';
GRANT ALL PRIVILEGES ON dvwa.* TO 'dvwa'@'localhost';
FLUSH PRIVILEGES;
"""

    run(["mysql", "-u", "root", "-e", sql])

    if config_file.exists():
        text = config_file.read_text(errors="ignore")

        text = text.replace(
            "$_DVWA[ 'db_user' ] = 'dvwa';",
            "$_DVWA[ 'db_user' ] = 'dvwa';"
        )

        text = text.replace(
            "$_DVWA[ 'db_password' ] = 'p@ssw0rd';",
            f"$_DVWA[ 'db_password' ] = '{db_password}';"
        )

        text = text.replace(
            "$_DVWA[ 'db_database' ] = 'dvwa';",
            "$_DVWA[ 'db_database' ] = 'dvwa';"
        )

        config_file.write_text(text)

    configure_dvwa_php_ini()

    run(["chown", "-R", f"{web_user}:{web_group}", str(dvwa_dir)])
    run(["chmod", "-R", "755", str(dvwa_dir)])

    if detect_package_manager() == "dnf":
        run(["setsebool", "-P", "httpd_can_network_connect_db", "1"], check=False)
        run([
            "chcon",
            "-R",
            "-t",
            "httpd_sys_rw_content_t",
            str(dvwa_dir / "hackable" / "uploads")
        ], check=False)

    run(["systemctl", "restart", web_service])

    print("\n[+] DVWA installed.")
    print("    URL: http://<server-ip>/dvwa")
    print("    Then click: Create / Reset Database")
    print(f"    Config: {config_file}")
    print(f"    DB user: dvwa")
    print(f"    DB password: {db_password}")


def install_node_stack():
    print("\n========== Installing Node.js tooling ==========")

    pkg_install(["nodejs", "npm"])

    if not command_exists("pnpm"):
        run(["npm", "install", "-g", "pnpm"])


def install_openclaw():
    print("\n========== Installing OpenClaw ==========")

    install_node_stack()
    clone_or_update(OPENCLAW_REPO, OPENCLAW_DIR)

    run(["pnpm", "install"], cwd=OPENCLAW_DIR)
    run(["pnpm", "ui:build"], cwd=OPENCLAW_DIR, check=False)
    run(["pnpm", "build"], cwd=OPENCLAW_DIR, check=False)
    run(["pnpm", "link", "--global"], cwd=OPENCLAW_DIR, check=False)

    print("\n[+] OpenClaw installed/cloned.")
    print("    Next manual step:")
    print("      openclaw onboard")
    print("    If using Ollama, check:")
    print("      curl http://127.0.0.1:11434/api/tags")


def install_metatron(repo_url):
    print("\n========== Installing Metatron ==========")

    if not repo_url:
        raise SystemExit("--metatron requires --metatron-repo https://github.com/OWNER/REPO.git")

    pm = detect_package_manager()

    if pm == "dnf":
        pkg_install(["git", "python3", "python3-pip", "python3-virtualenv"])
    else:
        pkg_install(["git", "python3", "python3-pip", "python3-venv"])

    clone_or_update(repo_url, METATRON_DIR)

    venv_dir = METATRON_DIR / "venv"

    if not venv_dir.exists():
        run(["python3", "-m", "venv", str(venv_dir)])

    pip = venv_dir / "bin" / "pip"

    run([str(pip), "install", "--upgrade", "pip", "setuptools", "wheel"])

    requirements = METATRON_DIR / "requirements.txt"
    if requirements.exists():
        run([str(pip), "install", "-r", str(requirements)])
    else:
        print("[!] No requirements.txt found. Skipping Python dependency install.")

    install_script = METATRON_DIR / "install.sh"
    if install_script.exists():
        run(["chmod", "+x", str(install_script)])
        run([str(install_script)], cwd=METATRON_DIR, check=False)

    print("\n[+] Metatron installed/cloned.")
    print(f"    Path: {METATRON_DIR}")
    print(f"    Activate: source {METATRON_DIR}/venv/bin/activate")


def main():
    parser = argparse.ArgumentParser(
        description="Install DVWA, Metatron, and OpenClaw modularly."
    )

    parser.add_argument("--all", action="store_true", help="Install all supported tools.")
    parser.add_argument("--base", action="store_true", help="Install only base packages.")
    parser.add_argument("--dvwa", action="store_true", help="Install DVWA.")
    parser.add_argument("--openclaw", action="store_true", help="Install OpenClaw.")
    parser.add_argument("--metatron", action="store_true", help="Install Metatron.")
    parser.add_argument("--metatron-repo", help="Git repo URL for Metatron.")

    args = parser.parse_args()

    require_root()
    detect_package_manager()
    install_base_packages()

    if args.base:
        print("\n[+] Base packages installed.")
        return

    if args.all or args.dvwa:
        install_dvwa()

    if args.all or args.openclaw:
        install_openclaw()

    if args.all or args.metatron:
        install_metatron(args.metatron_repo)

    if not any([args.all, args.base, args.dvwa, args.openclaw, args.metatron]):
        parser.print_help()
        return

    print("\n[+] Done.")


if __name__ == "__main__":
    main()