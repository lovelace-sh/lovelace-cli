# Lovelace CLI

A command-line tool for one-way synchronization from Cloudflare R2 to your local desktop, with live sync capabilities via WebSocket.

## Features

- 🔄 One-way sync from R2 to local directory
- 🔴 Live sync with WebSocket connection
- 🔐 Secure authentication with encrypted credentials
- 📦 Easy upgrade mechanism
- 🛡️ Automatic conflict resolution
- 📝 Comprehensive logging

## Installation

```bash
pip install lovelace
```

Or install from source:

```bash
git clone https://github.com/lovelace/lovelace-cli.git
cd lovelace-cli
pip install -e .
```

## Quick Start

### 1. Initialize Configuration

```bash
lovelace init
```

You'll be prompted for your username and password. The tool will authenticate with the Lovelace API and save your encrypted credentials to a `.lovelace` file in your current directory.

### 2. Sync Files

Perform a one-time sync:

```bash
lovelace sync
```

Preview what would be synced without making changes:

```bash
lovelace sync --dry-run
```

### 3. Watch for Changes

Start live sync that watches for changes:

```bash
lovelace watch
```

This will maintain a WebSocket connection and automatically sync changes as they occur on the remote.

## Commands

### `lovelace init`
Initialize or update your configuration. Creates a `.lovelace` file with encrypted credentials.

### `lovelace sync`
Perform a one-way sync from R2 to your local directory.

Options:
- `--dry-run`: Show what would be synced without making changes

### `lovelace watch`
Start watching for changes and sync automatically via WebSocket.

### `lovelace status`
Display current configuration and connection status.

### `lovelace reset`
Remove the current configuration file.

### `lovelace --upgrade`
Check for and install updates to the CLI tool.

### `lovelace --version`
Display the current version.

## Configuration

The `.lovelace` configuration file is created in your project root and contains:
- R2 bucket name and prefix
- Encrypted authentication credentials
- API endpoints

The file uses machine-specific encryption to protect your credentials.

## Advanced Usage

### Verbose Logging

Enable detailed logging:

```bash
lovelace sync --verbose
```

### Log to File

Save logs to a file:

```bash
lovelace sync --log-file sync.log
```

## Environment Variables

- `LOVELACE_API_URL`: Override the default API endpoint
- `LOVELACE_LOG_LEVEL`: Set logging level (DEBUG, INFO, WARNING, ERROR)

## Troubleshooting

### Authentication Issues

If you encounter authentication errors:

1. Check your credentials with `lovelace status`
2. Re-initialize with `lovelace init`
3. Ensure your account has proper permissions

### Sync Conflicts

The tool automatically handles conflicts by:
- Comparing file timestamps and hashes
- Prioritizing remote changes (one-way sync)
- Cleaning up local files not present on remote

### Connection Issues

For WebSocket connection problems:
- Check your network connectivity
- Verify firewall settings allow WebSocket connections
- Review logs with `--verbose` flag

## Development

### Setup Development Environment

```bash
git clone https://github.com/lovelace/lovelace-cli.git
cd lovelace-cli
pip install -e .
pip install -r requirements-dev.txt
```

### Running Tests

```bash
pytest tests/
```

### Building Package

```bash
python setup.py sdist bdist_wheel
```

## Support

For issues and feature requests, please visit:
https://github.com/lovelace/lovelace-cli/issues

## License

MIT License - see LICENSE file for details.

## Changelog

### Version 0.1.0
- Initial release
- One-way sync from R2 to local
- WebSocket-based live sync
- Encrypted configuration storage
- Auto-upgrade functionality