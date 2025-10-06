# Lovelace CLI

Command-line tool for syncing files from [Lovelace](https://lovelace.sh/) to your local machine with live updates.

## Installation

Install the Lovelace CLI:

```bash
pip install git+https://github.com/lovelace-sh/lovelace-cli.git
```

## Quick Start

### 1. Initialize Your Project

Navigate to an empty directory and run:

```bash
lovelace init
```

You'll be prompted for:
- Your username and password
- Which project to sync

This creates a `.lovelace` configuration file in your current directory.

### 2. Sync Your Files

One-time sync:

```bash
lovelace sync
```

Preview changes without syncing:

```bash
lovelace sync --dry-run
```

### 3. Live Sync (Watch Mode)

Automatically sync changes as they happen:

```bash
lovelace watch
```

Press `Ctrl+C` to stop.

## Commands

| Command | Description |
|---------|-------------|
| `lovelace init` | Set up a new project |
| `lovelace sync` | Sync files once |
| `lovelace sync --dry-run` | Preview what would sync |
| `lovelace watch` | Live sync (auto-updates) |
| `lovelace status` | Check configuration and token |
| `lovelace unlink` | Remove configuration |
| `lovelace --version` | Show version |
| `lovelace --upgrade` | Upgrade to latest version |

## Updating

The CLI automatically checks for updates before running commands. If a new version is available, you'll see:

```
⚠️  Update available: v0.1.0 → v0.2.0
   Run 'lovelace --upgrade' to update
```

To upgrade:

```bash
lovelace --upgrade
```

Or manually update with pip:

```bash
pip install --upgrade git+https://github.com/lovelace-sh/lovelace-cli.git
```

## How It Works

- **One-way sync**: Files sync from Lovelace to your local machine only
- **Secure**: Credentials are encrypted and stored in `.lovelace`
- **Live updates**: Watch mode uses WebSocket for instant sync
- **Automatic cleanup**: Removes local files deleted remotely

## Troubleshooting

**"No configuration found"**
- Run `lovelace init` in your project directory

**Authentication errors**
- Run `lovelace init` again to update credentials
- Check your credentials with `lovelace status`

**Connection issues in watch mode**
- Check your network connection
- Verify firewall allows WebSocket connections

## Support

Issues and questions: https://github.com/lovelace-sh/lovelace-cli/issues
