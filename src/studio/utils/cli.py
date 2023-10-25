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


def get_users(config: object, path: str) -> object:
    """Reads a csv and returns the users

    Parameters:
        config (object): CLI configuration object
        path (str): path to user csv file

    Returns:
        object: {'email':'team'}
    """

    users = {}

    with open(path, "r", newline="") as csvfile:
        csvreader = csv.reader(csvfile)
        for row in csvreader:
            # Check if each row has exactly two columns and the second column is a string
            if not len(row) == 2:
                click.secho("That's more columns than I was expecting", fg="red")
                sys.exit()

            try:
                int_value = int(row[1])
            except (ValueError, TypeError):
                click.secho(f"Team number provided is not an int: {row[1]}", fg="red")
                sys.exit()

            if not is_valid_email(row[0]):
                click.secho(f"{row[0]} is not a valid email address", fg="red")
                sys.exit()

            email = row[0].strip()
            team = str(row[1]).strip()
            users[email] = team

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
