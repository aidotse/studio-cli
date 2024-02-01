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

    table_name = get_or_create_table(region)

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
    # Reset DynamoDB
    clear_ddb(config)

    click.echo("\n** Setting up users... **")

    # Get users from provided csv
    users = get_users(config, path)

    # Create SM user profiles for each participant
    create_sagemaker_user_profiles(config, users.keys())

    # Create SM Space for each user
    create_sagemaker_spaces(config, users.keys())

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
    deleted_all_apps = False
    deleted_all_spaces = False
    deleted_all_users = False

    # Delete running SM apps in the SM domain
    deleted_all_apps = delete_apps(config)

    if deleted_all_apps:
        # Delete SM spaces in the SM domain
        deleted_all_spaces = delete_spaces(config)

    if deleted_all_spaces:
        # Delete SM user profiles
        deleted_all_users = delete_users(config)

    if deleted_all_users:
        # Reset DynamoDB
        clear_ddb(config)
        click.secho(
            "\nAll SageMaker assets have been deleted. If you've deployed a frontend don't forget to delete that as well.\n",
            fg="yellow",
        )

    # users = get_users_from_ddb(config)

    else:
        click.secho("\n\nCould not completely purge the environment", fg="red")
        click.secho("Try running the purge command again in a minute or two.", fg="red")
