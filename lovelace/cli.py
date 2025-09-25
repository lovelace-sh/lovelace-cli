#!/usr/bin/env python3

import click
import sys
import signal
import getpass
from pathlib import Path
from typing import Optional

from . import __version__
from .logger import setup_logging
from .config import ConfigManager, ConfigError
from .auth import AuthClient, AuthenticationError
from .sync import R2Sync, SyncError
from .watch import WebSocketWatcher, WatchError
from .upgrade import Upgrader, UpgradeError

@click.group(invoke_without_command=True)
@click.option('--upgrade', is_flag=True, help='Check for and install updates')
@click.option('--version', is_flag=True, help='Show version information')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--log-file', type=click.Path(), help='Path to log file')
@click.pass_context
def cli(ctx, upgrade, version, verbose, log_file):
    """Lovelace CLI - One-way sync from Cloudflare R2 to local"""
    
    log_path = Path(log_file) if log_file else None
    setup_logging(verbose=verbose, log_file=log_path)
    
    if version:
        click.echo(f"Lovelace CLI version {__version__}")
        ctx.exit()
    
    if upgrade:
        upgrader = Upgrader()
        success, message = upgrader.check_and_upgrade()
        click.echo(message)
        ctx.exit(0 if success else 1)
    
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

@cli.command()
def init():
    """Initialize Lovelace configuration"""
    
    import os
    current_dir = Path.cwd()
    dir_contents = list(current_dir.iterdir())
    non_hidden = [f for f in dir_contents if not f.name.startswith('.')]
    
    if non_hidden:
        click.echo("Error: Directory must be empty to initialize a Lovelace project", err=True)
        click.echo(f"Found {len(non_hidden)} file(s)/folder(s) in current directory", err=True)
        sys.exit(1)
    
    config_manager = ConfigManager()
    
    if config_manager.exists():
        if not click.confirm("Configuration already exists. Overwrite?"):
            click.echo("Initialization cancelled")
            return
    
    # Prompt for credentials after directory check
    username = click.prompt("Username")
    password = click.prompt("Password", hide_input=True)
    
    click.echo("Authenticating...")
    
    auth_client = AuthClient()
    
    try:
        auth_response = auth_client.authenticate(username, password)
        access_token = auth_response.get("access_token")
        projects = auth_response.get("projects", [])
        
        if not projects:
            click.echo("No projects available for your account", err=True)
            sys.exit(1)
        
        # Show login info if available
        if auth_response.get('username'):
            click.echo(f"\nLogged in as: {auth_response.get('username')}")
        click.echo(f"Found {len(projects)} project(s)")
        
        # Use inquirer for interactive selection
        import inquirer
        
        # Create choices list with formatted project names
        project_choices = []
        for project in projects:
            project_type = project.get('type', 'unknown')
            description = project.get('description', '')
            
            # Format display name
            display_name = f"{project['name']:<25} [{project_type:<5}] (ID: {project['id']})"
            if description:
                display_name += f" - {description}"
            
            project_choices.append((display_name, project))
        
        questions = [
            inquirer.List(
                'project',
                message="Select a project (use arrow keys)",
                choices=project_choices,
            )
        ]
        
        try:
            answers = inquirer.prompt(questions)
            if not answers:
                click.echo("Selection cancelled")
                return
            selected_project = answers['project']
        except (KeyboardInterrupt, EOFError):
            click.echo("\nSelection cancelled")
            return
        
        click.echo(f"\nConfiguring project: {selected_project['name']}...")
        
        # Get project-specific token and configuration using auto-generated device ID
        project_config = auth_client.get_project_token(access_token, selected_project['id'])
        
        config_manager.save(project_config)
        
        click.echo(f"\nConfiguration saved to {config_manager.config_path}")
        click.echo(f"Project: {project_config['project_name']}")
        click.echo(f"Bucket: {project_config['bucket']}")
        click.echo(f"Prefix: {project_config['prefix']}")
        click.echo(f"Device ID: {project_config.get('device_name', 'auto-generated')}")
        click.echo("\nInitialization complete!")
        
    except AuthenticationError as e:
        click.echo(f"Authentication failed: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)

@cli.command()
@click.option('--dry-run', is_flag=True, help='Show what would be synced without making changes')
def sync(dry_run):
    """Sync files from R2 to local directory"""
    
    config_manager = ConfigManager()
    
    if not config_manager.exists():
        click.echo("No configuration found. Please run 'lovelace init' first.", err=True)
        sys.exit(1)
    
    try:
        config = config_manager.load()
        
        click.echo(f"Syncing from bucket '{config['bucket']}' with prefix '{config['prefix']}'...")
        
        syncer = R2Sync(config)
        
        downloaded, updated, deleted = syncer.sync(dry_run=dry_run)
        
        if dry_run:
            click.echo("\nDry run results:")
        else:
            click.echo("\nSync complete:")
        
        if downloaded:
            click.echo(f"  Downloaded {len(downloaded)} new files")
            if len(downloaded) <= 10:
                for f in downloaded:
                    click.echo(f"    + {f}")
        
        if updated:
            click.echo(f"  Updated {len(updated)} files")
            if len(updated) <= 10:
                for f in updated:
                    click.echo(f"    ~ {f}")
        
        if deleted:
            click.echo(f"  Deleted {len(deleted)} files")
            if len(deleted) <= 10:
                for f in deleted:
                    click.echo(f"    - {f}")
        
        if not downloaded and not updated and not deleted:
            click.echo("  No changes needed")
        
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(1)
    except SyncError as e:
        click.echo(f"Sync error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)

@cli.command()
def watch():
    """Watch for changes and sync automatically"""
    
    config_manager = ConfigManager()
    
    if not config_manager.exists():
        click.echo("No configuration found. Please run 'lovelace init' first.", err=True)
        sys.exit(1)
    
    try:
        config = config_manager.load()
        
        click.echo(f"Starting live sync from bucket '{config['bucket']}' with prefix '{config['prefix']}'...")
        click.echo("Press Ctrl+C to stop")
        
        syncer = R2Sync(config)
        watcher = WebSocketWatcher(config, syncer)
        
        def signal_handler(sig, frame):
            click.echo("\nStopping watcher...")
            watcher.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        watcher.start()
        
        import time
        while watcher.running:
            time.sleep(1)
        
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(1)
    except WatchError as e:
        click.echo(f"Watch error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)

@cli.command()
def unlink():
    """Remove Lovelace configuration file"""
    
    config_manager = ConfigManager()
    
    if not config_manager.exists():
        click.echo("No configuration found")
        return
    
    config_manager.delete()
    click.echo("Configuration file removed")

@cli.command()
def status():
    """Show current configuration status"""
    
    config_manager = ConfigManager()
    
    if not config_manager.exists():
        click.echo("No configuration found. Please run 'lovelace init' first.")
        return
    
    try:
        config = config_manager.load()
        
        click.echo("Current configuration:")
        click.echo(f"  Config file: {config_manager.config_path}")
        click.echo(f"  Project: {config.get('project_name', 'N/A')}")
        click.echo(f"  Project ID: {config.get('project_id', 'N/A')}")
        click.echo(f"  Device: {config.get('device_name', 'N/A')}")
        click.echo(f"  Bucket: {config['bucket']}")
        click.echo(f"  Prefix: {config['prefix']}")
        click.echo(f"  Endpoint: {config['endpoint_url']}")
        
        auth_client = AuthClient()
        validation = auth_client.validate_token(config['token'])
        
        if validation.get("valid"):
            click.echo(f"  Token: Valid")
            
            # Update config if backend values changed
            updated = False
            if validation.get("prefix") and validation["prefix"] != config.get("prefix"):
                config["prefix"] = validation["prefix"]
                updated = True
            if validation.get("bucket") and validation["bucket"] != config.get("bucket"):
                config["bucket"] = validation["bucket"]
                updated = True
            if validation.get("endpoint_url") and validation["endpoint_url"] != config.get("endpoint_url"):
                config["endpoint_url"] = validation["endpoint_url"]
                updated = True
            if validation.get("websocket_url") and validation["websocket_url"] != config.get("websocket_url"):
                config["websocket_url"] = validation["websocket_url"]
                updated = True
            
            if updated:
                config_manager.save(config)
                click.echo("  Note: Configuration updated from server")
        else:
            click.echo(f"  Token: Invalid or expired")
        
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)

def main():
    cli()

if __name__ == '__main__':
    main()