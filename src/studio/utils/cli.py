import csv
import json
import os
import re
import sys
from functools import wraps

import click

STUDIO_CLI_CONFIG_PATH = "~/.studio_cli/config"


def store_configuration(config) -> None:
    """Stores studio cli configuration

    Returns:
        None
    """

    os.makedirs(
        os.path.dirname(os.path.expanduser(STUDIO_CLI_CONFIG_PATH)), exist_ok=True
    )
    with open(os.path.expanduser(STUDIO_CLI_CONFIG_PATH), "w") as file:
        json.dump(config, file, indent=2)
    return None


def get_configuration() -> object:
    """Gets the current persisted configuration

    Returns:
        object: Configuration data, or None
    """

    try:
        with open(os.path.expanduser(STUDIO_CLI_CONFIG_PATH), "r") as file:
            data = json.load(file)
            return data
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        click.secho(
            "Something went wrong when trying to read the configuration file...",
            fg="red",
        )

        return None


# Define a simple configuration check function
def is_configured() -> bool:
    conf = get_configuration()
    if conf:
        return True
    return False


# Decorator to ensure configuration is set
def require_cli_config(func):
    """Decorator for ensuring that there exists configuration for the CLI"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if is_configured():
            # User is authenticated, call the original function
            return func(*args, **kwargs)
        else:
            # User is not authenticated, handle the error or raise an exception
            click.secho(
                "It appears you haven't configured the CLI. Run 'studio configure' ",
                fg="red",
            )

    return wrapper


def get_users(config: object, path: str) -> dict:
    """Reads a csv and returns the users

    Parameters:
        config (object): CLI configuration object
        path (str): path to user csv file

    Returns:
        dict: {'email':'team'}
    """

    users = {}

    with open(path, "r", newline="") as csvfile:
        # Determine if the CSV has headers
        has_headers = csv.Sniffer().has_header(csvfile.read(1024))
        csvfile.seek(0)  # Rewind the file to the beginning

        csvreader = csv.reader(csvfile)
        header = next(csvreader) if has_headers else None

        for row in csvreader:
            try:
                email_index = header.index("email") if has_headers else 0
                team_index = header.index("team") if has_headers else 1

                email = row[email_index].strip()
                team = row[team_index].strip()

                if not email or not team:
                    raise ValueError("Email and team cannot be empty")

                if not is_valid_email(email):
                    raise ValueError(f"{email} is not a valid email address")

                if not team.isnumeric():
                    raise ValueError(
                        f"Team number provided is not a valid integer: {team}"
                    )

                users[email] = int(team)

            except ValueError as e:
                click.secho(f"Error processing CSV row: {e}", fg="red")
                sys.exit(1)
            except IndexError:
                click.secho("CSV format does not match expected structure", fg="red")
                sys.exit(1)

    if config.verbose:
        click.echo("Users:")
        click.echo(json.dumps(users, indent=2))
    return users


def is_valid_email(email):
    # Regular expression pattern for a basic email validation
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

    # Use re.match to check if the email matches the pattern
    if re.match(pattern, email):
        return True
    else:
        return False
