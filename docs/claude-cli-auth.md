# Claude CLI Authentication on PVE

This document describes how Claude CLI authentication is managed on the PVE infrastructure for the LLM News Service.

## Overview

Claude CLI uses OAuth-based subscription authentication (not API keys). Authentication tokens are centrally managed on the PVE host and synced to containers.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     PVE Host                                     │
│  /srv/aso/claude-auth/           ← Canonical OAuth credentials   │
│    ├── .credentials.json         ← OAuth token                   │
│    └── .claude.json              ← Main config                   │
└─────────────────────┬───────────────────────────────────────────┘
                      │ pct push (auth sync)
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│              Containers (700, 703, etc.)                         │
│  /root/.claude/                  ← Synced auth directory         │
│    └── .credentials.json         ← OAuth token                   │
│  /root/.claude.json              ← Config file                   │
│  /bin/claude                     ← Claude CLI                    │
└─────────────────────────────────────────────────────────────────┘
```

## Canonical Auth Location

Master OAuth credentials are stored on PVE host:
- **Path**: `/srv/aso/claude-auth/`
- **Owner**: `aso-ops:aso-ops`
- **Files**:
  - `.credentials.json` (600 perms) - OAuth token
  - `.claude.json` (600 perms) - Claude CLI config

## Syncing Auth to Containers

To sync credentials to a container, run from PVE host:

```bash
# Create .claude directory
pct exec <CTID> -- mkdir -p /root/.claude

# Push credentials
pct push <CTID> /srv/aso/claude-auth/.credentials.json /root/.claude/.credentials.json
pct exec <CTID> -- chmod 600 /root/.claude/.credentials.json

# Push config
pct push <CTID> /srv/aso/claude-auth/.claude.json /root/.claude.json
pct exec <CTID> -- chmod 600 /root/.claude.json
```

Or use the sync script:
```bash
/opt/aso/aso_platform/agent-pool/bin/wp-017-sync-auth.sh <CTID>
```

## Verification

Verify auth works after syncing:

```bash
# Check version
pct exec <CTID> -- claude --version

# Test prompt
pct exec <CTID> -- bash -c 'echo "Say OK" | claude -p'
```

## Token Refresh

OAuth tokens expire periodically. To refresh:

1. SSH to PVE host
2. Run `claude auth login` (or `claude login`)
3. Complete OAuth flow in browser
4. Sync new credentials to containers

## Containers Using Claude CLI

| CTID | Name             | IP             | Purpose                    |
|------|------------------|----------------|----------------------------|
| 700  | fantasyedge      | 192.168.7.126  | FantasyEdge ML platform    |
| 703  | llm-news-service | 192.168.6.75   | LLM News Intelligence      |

## Usage in Code

### Simple prompt (print mode)
```python
import subprocess

def call_claude(prompt: str) -> str:
    result = subprocess.run(
        ["claude", "-p", "--max-turns", "1"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.stdout.strip()
```

### With specific model
```python
result = subprocess.run(
    ["claude", "-p", "--model", "claude-opus-4-5-20251101", "--max-turns", "1"],
    input=prompt,
    capture_output=True,
    text=True,
)
```

### JSON output format
```python
result = subprocess.run(
    ["claude", "-p", "--output-format", "json", "--max-turns", "1"],
    input=prompt,
    capture_output=True,
    text=True,
)
data = json.loads(result.stdout)
# data = {"result": "...", "usage": {"input_tokens": N, "output_tokens": N}}
```

## References

- ASO WP-017: Claude CLI Migration (`C:\code\aso-repo\ops\workpackages\wp-017-claude-cli-migration\`)
- ASO Claude Client (`C:\code\aso4\services\common\claude_client.py`)
