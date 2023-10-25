import click
from studio.utils.cli import *
from studio.utils.aws import *
import json


class Config(object):
    def __init__(self) -> None:
        self.verbose = False
        self.update_from_conf_file()

    ALLOWED_KEYS = ["verbose", "region", "domain_id", "table_name"]

    # Merge existing conf with Config object
    def update_from_conf_file(self):
        conf = get_configuration()
        if conf:
            for key, value in conf.items():
                if key in self.ALLOWED_KEYS:
                    setattr(self, key, value)


pass_config = click.make_pass_decorator(Config, ensure=True)


@click.group()
@click.option("-v", "--verbose", is_flag=True)
@pass_config
def cli(config, verbose):
    config.verbose = verbose


@cli.command()
def configure():
    """Configures the hackathon CLI with relevant information"""
    region = click.prompt(
        "What AWS region do you want to use?", type=str, default="eu-west-1"
    )

    domain_id = ""

    while not domain_id.startswith("d-"):
        if domain_id:
            click.secho("That's not the Domain ID, and you know it", fg="red")
        domain_id = click.prompt("Enter the SageMaker Studio Domain ID", type=str)

    table_name = get_or_create_table()

    store_configuration(
        {"region": region, "domain_id": domain_id, "table_name": table_name}
    )

    click.secho("\n\U0001F973 studio cli is now ready to be used", fg="cyan")
    click.secho(
        f'\nIf you ever need to reconfigure the cli, just run "studio configure"',
        fg="white",
    )


@cli.command()
@pass_config
@require_cli_config
def get_conf(config):
    """Prints current configuration"""
    click.secho(json.dumps(get_configuration(), indent=3), fg="cyan")


@cli.command()
@pass_config
@require_cli_config
@click.argument("path", type=click.Path(exists=True))
def setup_users(config, path):
    """Creates users and teams"""

    click.echo("Setting up users...")

    # Reset DynamoDB
    clear_ddb(config)

    # Get users from provided csv
    users = get_users(config, path)

    # Create SM user profiles for each participant
    create_sagemaker_user_profiles(config, users.keys())

    # Create SM Spaces for each team
    create_sagemaker_spaces(config, users.values())

    # Store users in DDB for downstream usage.
    add_users_to_ddb(config, users)


@cli.command()
@pass_config
@require_cli_config
def get_urls(config):
    """Get login urls for each user profile"""
    click.echo("Getting presigned urls... ")

    # Get users from state in DDB
    users = get_users_from_ddb(config)

    # Get presigned urls
    urls = get_presigned_urls(config, users)

    if urls:
        click.echo("Presigned URLs: \n")

        click.echo(json.dumps(urls, indent=2))


@cli.command()
@pass_config
@require_cli_config
def purge(config):
    """Deletes all Hackathon SM User profiles, running SM apps, SM spaces etc."""

    # Get users from state in DDB
    users = get_users_from_ddb(config)

    # Delete SM user profiles
    delete_users(config, users.keys())

    # Delete running SM apps in the SM domain
    delete_apps(config)

    # Delete SM spaces in the SM domain
    delete_spaces(config)

    # Reset DynamoDB
    clear_ddb(config)
