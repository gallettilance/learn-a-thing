# Local Setup

Cloud automation is not used. Everything runs on your Mac.

## 1. Virtual environment

```bash
cd /Users/lance/Documents/RedHat/research
python3 -m venv .venv
source .venv/bin/activate
pip install -r orchestrator/requirements.txt -r site/requirements.txt
```

## 2. API key

Get a key from [Cursor Dashboard → Integrations](https://cursor.com/dashboard/integrations):

```bash
export CURSOR_API_KEY="cursor_..."
# Add to ~/.zshrc for persistence
```

## 3. Run pipeline

```bash
./scripts/nightly-local.sh
```

## 4. Read in browser

```bash
python site/serve.py
```

Open http://127.0.0.1:8765/

## 5. Schedule 11pm runs

```bash
chmod +x scripts/install-schedule.sh scripts/nightly-local.sh
./scripts/install-schedule.sh
```

Edit `~/Library/LaunchAgents/com.research.nightly-learning.plist` to add `CURSOR_API_KEY` under `EnvironmentVariables` if not in your shell profile.

## Optional: Git remote

Push is off by default. To push after nightly runs:

```bash
python orchestrator/nightly.py --push
```
