# IDEM  Deploy Agent

---

**Deploy Agent** is a lightweight service that runs on your VPS.
It connects to the orchestration platform (`ORCH_URL`) and automates the deployment of containerized applications on your infrastructure.

---

## ✨ Key Features

* 🔑 **Agent registration** → securely registers with the orchestrator (`/register`)
* 📡 **Job polling** → fetches pending deployment jobs (`/poll_jobs`) authenticated via token
* ⚙️ **Automated deployments** → executes deployment scripts (`deploy_app_with_certs.sh`, `deploy-spa-app.sh`) for both standard and SPA apps
* 🔐 **Secure environment management** → retrieves environment variables from the orchestrator and writes `.env` files with strict permissions
* 📝 **Job reporting** → sends job execution status and logs back to the orchestrator (`/report`)
* ⚡ **Systemd integration** → runs as a background service and restarts automatically on failures

---

## 🏗️ Architecture Overview

1. **Orchestrator** sends jobs to registered agents.
2. **Deploy Agent** running on the VPS polls for jobs.
3. On receiving a job:

   * Downloads required environment variables from the orchestrator
   * Creates a `.env` file under `/opt/apps/<app>/`
   * Executes the appropriate deployment script inside the VPS
   * Reports results and logs back to the orchestrator
4. The service runs continuously under `systemd`, ensuring reliability and self-healing.

---

## 📥 Installation

On your VPS, run the following one-liner:

```bash
curl -fsSL https://github.com/Idem-AI/deploy-agent/releases/download/v1.0.0/vps-agent.sh | sudo bash -s -- https://orchestrator.idem.africa
```

👉 Replace `https://orchestratoridem.africam` with your orchestrator URL.

To skip bootstrap preparation:

```bash
curl -fsSL https://github.com/Idem-AI/deploy-agent/releases/download/v1.0.0/install-agent.sh | sudo bash -s -- https://orchestrator.idem.africa --no-bootstrap
```

---

## 🔍 Verification

Check if the agent service is running:

```bash
systemctl status deploy-agent.service
```

Follow logs in real time:

```bash
journalctl -u deploy-agent.service -f
```

---

## 🔄 Updating the Agent

To upgrade to the **latest release**:

```bash
curl -fsSL https://github.com/Idem-AI/deploy-agent/releases/latest/download/vps-agent.sh | sudo bash -s -- https://orchestrator.idem.africa
```

The installer will:

* Download the newest agent and bootstrap scripts from the GitHub Release
* Update the Python virtual environment
* Restart the systemd service

---

## 🛡️ Security Considerations

* ✅ All artifacts (vps-agent.sh`, `agent.py`, `bootstrap.sh`) are distributed via **GitHub Releases**, ensuring immutability and trust.
* ✅ Tokens are stored locally at `/etc/deploy-agent/token.json` with `600` permissions.
* ✅ The agent runs as `root` to manage deployments but is sandboxed through strict directory usage (`/opt/deploy-agent`, `/opt/apps`).
* ✅ Environment variables are written securely into `.env` files with `600` permissions to prevent leaks.
* 🔒 Optionally, release files can be distributed with SHA256 checksums or GPG signatures for extra verification.

---

## 📦 Deployment Scripts

By default, the agent expects the following scripts to be present:

* **`deploy_app_with_certs.sh`** → deploys containerized applications with SSL certificates
* **`deploy-spa-app.sh`** → deploys SPA (Single Page Application) apps

These scripts should be stored in `/opt/` and will be executed automatically by the agent.

---

## ⚙️ Environment Variables

The agent behavior can be customized via environment variables (configured in the systemd unit):

| Variable             | Default                         | Description                                      |
| -------------------- | ------------------------------- | ------------------------------------------------ |
| `ORCH_URL`           | `http://localhost:8000`         | Orchestrator URL                                 |
| `DEPLOY_CERT_SCRIPT` | `/opt/deploy_app_with_certs.sh` | Script for standard containerized app deployment |
| `DEPLOY_SPA_SCRIPT`  | `/opt/deploy-spa-app.sh`        | Script for SPA deployments                       |
| `POLL_INTERVAL`      | `10` seconds                    | Interval between job polls                       |
| `TOKEN_FILE`         | `/etc/deploy-agent/token.json`  | Location of the agent’s authentication token     |
| `JOB_TIMEOUT`        | `3600` seconds (1 hour)         | Maximum execution time per job                   |
| `MAX_OUTPUT_LENGTH`  | `20000` characters              | Maximum output length stored and reported        |

---

## 📊 Example Workflow

1. User pushes code → orchestrator generates a deployment job
2. Deploy Agent polls `/poll_jobs` and receives the job
3. Agent fetches environment variables (e.g. DB credentials, API keys)
4. Agent writes `.env` under `/opt/apps/myapp/`
5. Agent executes `deploy_app_with_certs.sh myapp-repo.git`
6. Logs and status are reported back to the orchestrator

---

## 🧪 Local Testing

You can run the agent manually for one-shot deployment:

```bash
python3 agent.py --once --repo https://github.com/example/myapp.git --domain myapp.com
```

This will:

* Create the `/opt/apps/myapp/.env` file
* Run the deployment script in the app directory

---

## 🗺️ Roadmap / Future Improvements

Planned enhancements for upcoming versions of Deploy Agent:

* 🔄 **Auto-update mechanism** → agent can self-update by pulling the latest GitHub Release
* 🛡️ **GPG-signed releases** → provide cryptographic verification of downloaded artifacts
* 📦 **Containerized agent** → distribute agent as a Docker container for even easier installation
* 🔔 **Monitoring & metrics** → expose Prometheus/OpenTelemetry metrics for observability
* 🖥️ **Multi-user support** → allow non-root execution with elevated privileges only when required
* 🕹️ **CLI tools** → provide a `deploy-agent` CLI to manually trigger jobs and check status
* 🌍 **Multi-orchestrator support** → connect a single agent to multiple orchestrators
* 🚨 **Enhanced failure handling** → smarter retry strategies, job prioritization, and alerting

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

---
