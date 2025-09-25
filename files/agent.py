#!/usr/bin/env python3
"""
agent_caseB.py - Minimal deployment agent for client VPS (Case B)

Fonctionnalités :
 - register (POST /register) -> stocke agent_id + agent_token localement (TOKEN_FILE)
 - poll /poll_jobs (X-AGENT-TOKEN) -> récupère jobs pending
 - si job.env_token présent -> GET /download_env?env_token=... pour récupérer env.json
 - écrit /opt/apps/<app>/.env (mode 600) avant d'exécuter le script
 - exécute script (whitelist /opt/apps) et POST /report avec résultat
"""
import os
import time
import json
import socket
import argparse
import requests
import subprocess
from pathlib import Path


# Config via env
APP_DIR = os.environ.get("APP_DIR" , "/opt/vps-deployment/apps")
DEPLOY_CERT_SCRIPT = os.environ.get("DEPLOY_CERT_SCRIPT", "/opt/vps-deployment/deploy_app_with_certs.sh")
DEPLOY_SPA_SCRIPT  = os.environ.get("DEPLOY_SPA_SCRIPT",  "/opt/vps-deployment/deploy_spa_with_certs.sh")
ORCH_URL = os.environ.get("ORCH_URL", "http://107.23.168.136:8000").rstrip("/")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "10"))
TOKEN_FILE = os.environ.get("TOKEN_FILE", "/etc/deploy-agent/token.json")
AGENT_HOSTNAME = os.environ.get("AGENT_HOSTNAME", socket.gethostname())
JOB_TIMEOUT = int(os.environ.get("JOB_TIMEOUT", "3600"))
MAX_OUTPUT_LENGTH = int(os.environ.get("MAX_OUTPUT_LENGTH", "20000"))
running_jobs = set()

Path(os.path.dirname(TOKEN_FILE) or "/etc/deploy-agent").mkdir(parents=True, exist_ok=True)

# ------------------------
# Gestion des tokens
# ------------------------
def save_token(agent_id: str, token: str):
    data = {"agent_id": agent_id, "token": token}
    tmp = TOKEN_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh)
    os.chmod(tmp, 0o600)
    os.replace(tmp, TOKEN_FILE)
    print(f"[agent] saved token to {TOKEN_FILE}")

def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "r") as fh:
        return json.load(fh)

def register():
    url = ORCH_URL + "/register"
    payload = {"hostname": AGENT_HOSTNAME, "ip": "", "ssh_pubkey": "", "meta": {}}
    print("[agent] registering ...")
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()
    j = r.json()
    save_token(j["agent_id"], j["agent_token"])
    return j["agent_id"], j["agent_token"]

def find_token_or_register():
    tok = load_token()
    if tok and tok.get("token"):
        return tok["agent_id"], tok["token"]
    return register()

# ------------------------
# Polling et reporting
# ------------------------
def poll_jobs(agent_token: str):
    url = ORCH_URL + "/poll_jobs"
    headers = {"X-AGENT-TOKEN": agent_token}
    try:
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code == 403:
            print("[agent] token invalid (403)")
            return None
        r.raise_for_status()
        return r.json().get("jobs", [])
    except Exception as e:
        print("[agent] poll error:", e)
        return None

def truncate(text: str, length: int) -> str:
    if not isinstance(text, str):
        text = str(text)
    if len(text) <= length:
        return text
    return text[:length] + "\n...[truncated]..."

def report_result(agent_token: str, job_id: str, status: str, output: str):
    url = ORCH_URL + "/report"
    headers = {"X-AGENT-TOKEN": agent_token, "Content-Type": "application/json"}
    payload = {"job_id": job_id, "status": status, "output": output}
    for attempt in range(3):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            r.raise_for_status()
            return True
        except Exception as e:
            print(f"[agent] report attempt {attempt+1} failed:", e)
            time.sleep(2 ** attempt)
    print("[agent] failed to report after retries")
    return False

# ------------------------
# Gestion des .env et exécution
# ------------------------
def write_env_for_app(repo_url: str, env_dict: dict):
    app_name = os.path.basename(repo_url).replace(".git", "")
    app_dir = "$APP_DIR"
    os.makedirs(app_dir, exist_ok=True)
    # convert to .env bytes
    lines = []
    for k, v in env_dict.items():
        s = "" if v is None else str(v)
        safe = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        lines.append(f'{k}="{safe}"')
    data = ("\n".join(lines) + "\n").encode("utf-8")
    tmp = os.path.join(app_dir, ".env.tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, os.path.join(app_dir, ".env"))
    os.chmod(os.path.join(app_dir, ".env"), 0o600)
    print(f"[agent] wrote .env for {app_name} at {app_dir}/.env")
    return app_dir

def execute_job(job: dict, agent_token: str):
    job_id = job.get("job_id")
    args = job.get("args", [])
    env_token = job.get("env_token")
    is_spa = job.get("is_spa")
    global running_jobs

    if job_id in running_jobs:
        print(f"[agent] job {job_id} already running, skipping")
        return
    running_jobs.add(job_id)

    try:
        print(f"[agent] executing job {job_id}...")
        script =  DEPLOY_CERT_SCRIPT

        # récupérer les variables d'environnement
        cwd = "/"
        if env_token:
            try:
                r = requests.get(
                    f"{ORCH_URL}/download_env",
                    params={"env_token": env_token},
                    headers={"X-AGENT-TOKEN": agent_token},
                    timeout=30,
                )
                r.raise_for_status()
                env_json = r.json()
                cwd = write_env_for_app(args[0] if args else "unknown", env_json)
            except Exception as e:
                print("[agent] failed to download env:", e)
                report_result(agent_token, job_id, "failed", f"failed to download env: {e}")
                return

        # exécuter le script
        try:
            proc = subprocess.run(
                [script] + args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=JOB_TIMEOUT,
            )
            out = proc.stdout + "\n" + proc.stderr
            out = truncate(out, MAX_OUTPUT_LENGTH)
            status = "done" if proc.returncode == 0 else "failed"
            report_result(agent_token, job_id, status, out)
        except subprocess.TimeoutExpired:
            report_result(agent_token, job_id, "failed", f"timeout after {JOB_TIMEOUT}s")
        except Exception as e:
            report_result(agent_token, job_id, "failed", f"exception: {e}")

    finally:
        running_jobs.remove(job_id)

# ------------------------
# Boucle principale
# ------------------------
def poll_loop():
    global running_jobs
    try:
        agent_id, token = find_token_or_register()
    except Exception as e:
        print("[agent] register failed:", e)
        time.sleep(30)
        return

    print(f"[agent] starting poll loop as {agent_id}")
    while True:
        # 👉 Ne poll que si aucun job en cours
        if running_jobs:
            time.sleep(POLL_INTERVAL)
            continue

        jobs = poll_jobs(token)
        if jobs is None:
            # token invalid -> try register again
            try:
                agent_id, token = register()
            except Exception:
                time.sleep(POLL_INTERVAL)
                continue

        if jobs:
            for job in jobs:
                try:
                    execute_job(job, token)
                except Exception as e:
                    print("[agent] job error:", e)

        time.sleep(POLL_INTERVAL)

# ------------------------
# Entrée principale
# ------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="Run one local deploy (useful for bootstrap)")
    ap.add_argument("--repo", help="Repo URL for one-shot")
    ap.add_argument("--domain", help="Domain for one-shot")
    ap.add_argument("--spa", action="store_true", help="is spa for one-shot")
    args = ap.parse_args()

    # Mode bootstrap
    if args.once:
        if not args.repo:
            print("repo required with --once")
            return
        app_name = os.path.basename(args.repo).replace(".git", "")
        app_dir = os.path.join("/opt/apps", app_name)
        candidates = [
            os.path.join(app_dir, "deploy_app_with_certs.sh"),
            os.path.join("/opt/apps", "deploy_app_with_certs.sh"),
        ]
        script = next((c for c in candidates if os.path.exists(c) and os.access(c, os.X_OK)), None)
        if not script:
            print("no script found")
            return
        cmd = [script, args.repo]
        if args.domain:
            cmd.append(args.domain)
        print("[agent] running local script:", cmd)
        subprocess.run(cmd, cwd=app_dir if os.path.isdir(app_dir) else "/")
        return

    # Mode normal : boucle infinie
    try:
        poll_loop()
    except KeyboardInterrupt:
        print("[agent] interrupted")
        return

if __name__ == "__main__":
    main()
