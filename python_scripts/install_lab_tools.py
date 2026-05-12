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
  sudo python3 install_lab_tools.py --dvwa
  sudo python3 install_lab_tools.py --openclaw
  sudo python3 install_lab_tools.py --metatron 
  sudo python3 install_lab_tools.py --all 
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
METATRON_REPO = "https://github.com/sooryathejas/METATRON.git"
PKG_MANAGER = None

WHATWEB_REPO = "https://github.com/urbanadventurer/WhatWeb.git"
NIKTO_REPO = "https://github.com/sullo/nikto.git"

WHATWEB_DIR = OPT_ROOT / "whatweb"
NIKTO_DIR = OPT_ROOT / "nikto"



def run(cmd, cwd=None, check=True):
    env = os.environ.copy()
    env["PATH"] = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + env.get("PATH", "")

    print(f"\n[+] Running: {' '.join(str(x) for x in cmd)}")
    subprocess.run(cmd, cwd=cwd, check=check, env=env)


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

def install_node_24():
    print("\n========== Installing Node.js 24 ==========")

    pm = detect_package_manager()

    if pm == "dnf":
        pkg_install(["curl"])
        run(["bash", "-c", "curl -fsSL https://rpm.nodesource.com/setup_24.x | bash -"])
        pkg_install(["nodejs"])

    elif pm == "apt":
        pkg_install(["curl", "ca-certificates"])
        run(["bash", "-c", "curl -fsSL https://deb.nodesource.com/setup_24.x | bash -"])
        pkg_install(["nodejs"])

    run(["node", "--version"])
    run(["npm", "--version"])

def clone_or_update(repo_url, dest):
    dest = Path(dest)

    if dest.exists() and (dest / ".git").exists():
        run(["git", "config", "--global", "--add", "safe.directory", str(dest)], check=False)
        run(["git", "pull"], cwd=dest)
    elif dest.exists():
        print(f"[!] {dest} exists but is not a git repo. Skipping clone.")
    else:
        run(["git", "clone", repo_url, str(dest)])

def install_base_packages():
    pm = detect_package_manager()

    pkg_install([
            "git",
            "curl",
            "wget",
            "unzip",
            "tar",
            "python3",
            "python3-pip"
        ])
    # if pm == "dnf":
    #     pkg_install([])
    # else:
    #     pkg_install([])

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
    arch = subprocess.check_output(["uname", "-m"], text=True).strip()

    if arch == "x86_64":
        node_arch = "x64"
    elif arch == "aarch64":
        node_arch = "arm64"
    else:
        raise SystemExit(f"Unsupported architecture for Node binary install: {arch}")

    version = "24.11.1"
    tarball = f"node-v{version}-linux-{node_arch}.tar.xz"
    url = f"https://nodejs.org/dist/v{version}/{tarball}"

    pkg_install(["curl", "xz"])

    run(["curl", "-fsSLO", url], cwd="/tmp")
    run(["tar", "-xJf", f"/tmp/{tarball}", "-C", "/usr/local", "--strip-components=1"])

    run(["bash", "-lc", "export PATH=/usr/local/bin:$PATH && hash -r && node --version && npm --version"])

    # if not command_exists("pnpm"):
    #     run(["npm", "install", "-g", "pnpm"])


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

def install_whatweb_from_source():
    print("\n========== Installing WhatWeb from source ==========")

    pkg_install(["git", "ruby", "rubygems"])

    clone_or_update(WHATWEB_REPO, WHATWEB_DIR)

    whatweb_exe = WHATWEB_DIR / "whatweb"

    if not whatweb_exe.exists():
        print(f"[!] WhatWeb executable not found at {whatweb_exe}")
        return

    run(["chmod", "+x", str(whatweb_exe)])
    run(["ln", "-sf", str(whatweb_exe), "/usr/local/bin/whatweb"])

    run(["whatweb", "--version"], check=False)


def install_nikto_from_source():
    print("\n========== Installing Nikto from source ==========")

    pkg_install(["git", "perl", "perl-core", "openssl"])

    clone_or_update(NIKTO_REPO, NIKTO_DIR)

    nikto_exe = NIKTO_DIR / "program" / "nikto.pl"

    if not nikto_exe.exists():
        print(f"[!] Nikto executable not found at {nikto_exe}")
        return

    run(["chmod", "+x", str(nikto_exe)])

    wrapper = Path("/usr/local/bin/nikto")
    wrapper.write_text(f"""#!/usr/bin/env bash
perl "{nikto_exe}" "$@"
""")
    run(["chmod", "+x", str(wrapper)])

    run(["nikto", "-Version"], check=False)

def install_ollama_and_metatron_model():
    print("\n========== Installing Ollama and METATRON model ==========")

    if not command_exists("ollama"):
        run(["bash", "-lc", "curl -fsSL https://ollama.com/install.sh | sh"])

    run(["systemctl", "enable", "--now", "ollama"], check=False)

    # 9B needs about 8.4GB+ RAM. Use 4B fallback for small VMs.
    mem_kb = 0
    with open("/proc/meminfo", "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("MemTotal:"):
                mem_kb = int(line.split()[1])
                break

    mem_gb = mem_kb / 1024 / 1024

    if mem_gb >= 9:
        base_model = "huihui_ai/qwen3.5-abliterated:9b"
    else:
        base_model = "huihui_ai/qwen3.5-abliterated:4b"

    print(f"[+] Detected RAM: {mem_gb:.2f} GB")
    print(f"[+] Pulling base model: {base_model}")

    run(["ollama", "pull", base_model])

    modelfile = METATRON_DIR / "Modelfile"

    if not modelfile.exists():
        print("[!] Modelfile not found. Cannot create metatron-qwen.")
        return

    # If using 4B fallback, patch FROM line.
    if "4b" in base_model:
        text = modelfile.read_text(errors="ignore")
        lines = text.splitlines()
        patched = []

        for line in lines:
            if line.strip().startswith("FROM "):
                patched.append(f"FROM {base_model}")
            else:
                patched.append(line)

        modelfile.write_text("\n".join(patched) + "\n")

    run(["ollama", "create", "metatron-qwen", "-f", str(modelfile)])
    run(["ollama", "list"], check=False)

def setup_metatron_database():
    print("\n========== Setting up METATRON MariaDB database ==========")

    sql = """
CREATE DATABASE IF NOT EXISTS metatron;
CREATE USER IF NOT EXISTS 'metatron'@'localhost' IDENTIFIED BY '123';
GRANT ALL PRIVILEGES ON metatron.* TO 'metatron'@'localhost';
FLUSH PRIVILEGES;

USE metatron;

CREATE TABLE IF NOT EXISTS history (
  sl_no INT AUTO_INCREMENT PRIMARY KEY,
  target VARCHAR(255) NOT NULL,
  scan_date DATETIME NOT NULL,
  status VARCHAR(50) DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS vulnerabilities (
  id INT AUTO_INCREMENT PRIMARY KEY,
  sl_no INT,
  vuln_name TEXT,
  severity VARCHAR(50),
  port VARCHAR(20),
  service VARCHAR(100),
  description TEXT,
  FOREIGN KEY (sl_no) REFERENCES history(sl_no)
);

CREATE TABLE IF NOT EXISTS fixes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  sl_no INT,
  vuln_id INT,
  fix_text TEXT,
  source VARCHAR(50),
  FOREIGN KEY (sl_no) REFERENCES history(sl_no),
  FOREIGN KEY (vuln_id) REFERENCES vulnerabilities(id)
);

CREATE TABLE IF NOT EXISTS exploits_attempted (
  id INT AUTO_INCREMENT PRIMARY KEY,
  sl_no INT,
  exploit_name TEXT,
  tool_used TEXT,
  payload LONGTEXT,
  result TEXT,
  notes TEXT,
  FOREIGN KEY (sl_no) REFERENCES history(sl_no)
);

CREATE TABLE IF NOT EXISTS summary (
  id INT AUTO_INCREMENT PRIMARY KEY,
  sl_no INT,
  raw_scan LONGTEXT,
  ai_analysis LONGTEXT,
  risk_level VARCHAR(50),
  generated_at DATETIME,
  FOREIGN KEY (sl_no) REFERENCES history(sl_no)
);
"""
    run(["mysql", "-u", "root", "-e", sql])


def install_metatron():
    print("\n========== Installing METATRON ==========")

    pm = detect_package_manager()
    db_service = "mariadb"

    pkg_install([
        "git",
        "python3",
        "python3-pip",
        "python3-venv",
        "mariadb-server",
        "nmap",
        "whois",
        "curl",
        "dnsutils",
        "zstd"
    ])
    if pm == "dnf":
        # RHEL/Rocky/Alma usually do not provide whatweb/nikto cleanly
        # from base repos, so install those from source below.
        install_whatweb_from_source()
        install_nikto_from_source()

    else:
        # Debian/Ubuntu/Kali usually package these directly.
        pkg_install([
            "whatweb",
            "nikto",
        ])

    enable_service(db_service)
    clone_or_update(METATRON_REPO, METATRON_DIR)
    venv_dir = METATRON_DIR / "venv"

    if not venv_dir.exists():
        run(["python3", "-m", "venv", str(venv_dir)])

    pip = "pip3"

    run([str(pip), "install", "--upgrade", "pip", "setuptools", "wheel"])

    requirements = METATRON_DIR / "requirements.txt"

    if requirements.exists():
        run([str(pip), "install", "-r", str(requirements)])
    else:
        print("[!] No requirements.txt found. Skipping Python dependency install.")

    install_ollama_and_metatron_model()
    setup_metatron_database()

    print("\n[+] METATRON installed.")
    print(f"    Path: {METATRON_DIR}")


def main():
    parser = argparse.ArgumentParser(description="Install DVWA, Metatron, and OpenClaw modularly.")

    parser.add_argument("--all", action="store_true", help="Install all supported tools.")
    parser.add_argument("--base", action="store_true", help="Install only base packages.")
    parser.add_argument("--dvwa", action="store_true", help="Install DVWA.")
    parser.add_argument("--openclaw", action="store_true", help="Install OpenClaw.")
    parser.add_argument("--metatron", action="store_true", help="Install Metatron.")

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
        install_metatron()

    if not any([args.all, args.base, args.dvwa, args.openclaw, args.metatron]):
        parser.print_help()
        return

    print("\n[+] Done.")


if __name__ == "__main__":
    main()