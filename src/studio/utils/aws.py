import boto3
import click
import time
import re
from concurrent.futures import ThreadPoolExecutor


def getUsernameFromEmail(email: str) -> str:
    """Gets username from email

    Parameters:
        email (str): an email adress

    Returns:
        str: username
    """
    username = re.sub(r"[^a-zA-Z0-9]+", "", email.split("@")[0])

    return username


def create_sagemaker_user_profiles(config: object, users: list) -> None:
    """Create SageMaker Studio user profiles

    Parameters:
        config (object): CLI configuration object.
        users (list): List of user emails

    Returns:
        None
    """

    sm_client = boto3.client("sagemaker", config.region)

    with click.progressbar(users, label="Creating SM user profiles") as users_list:
        for user_email in users_list:
            username = getUsernameFromEmail(user_email)
            try:
                sm_client.describe_user_profile(
                    DomainId=config.domain_id, UserProfileName=username
                )

            except sm_client.exceptions.ResourceNotFound:
                # User does not exist. Creating user.

                try:
                    sm_client.create_user_profile(
                        DomainId=config.domain_id, UserProfileName=username
                    )

                except:
                    click.secho(
                        f"User with name '{user_email}' could not be created for some reason. Skipping",
                        fg="red",
                    )
    return


def create_sagemaker_spaces(config: object, team_list: list) -> None:
    """Create SageMaker Studio Domain spaces for each item in the team_list

    Parameters:
        config (object): CLI configuration object.
        team_list (list): List of teams

    Returns:
        None
    """

    sm_client = boto3.client("sagemaker", config.region)

    with click.progressbar(team_list, label="Creating SM team spaces") as teams:
        for team in teams:
            try:
                sm_client.describe_space(DomainId=config.domain_id, SpaceName=str(team))
            except sm_client.exceptions.ResourceNotFound:
                # Space does not exist. Create space
                try:
                    sm_client.create_space(
                        DomainId=config.domain_id, SpaceName=str(team)
                    )
                except Exception as e:
                    click.secho(
                        f"Space with name '{team}' could not be created for some reason. Skipping\n\n {str(e)}",
                        fg="red",
                    )
                    click

    return


def add_users_to_ddb(config: object, users: object) -> None:
    """Stores all users and teams in DDB for easier state management"""

    ddb_client = boto3.resource("dynamodb", config.region)
    table_resource = ddb_client.Table(config.table_name)
    try:
        with table_resource.batch_writer() as batch:
            for user_email, team in users.items():
                batch.put_item(
                    Item={"pk": user_email, "team": team, "domain-id": config.domain_id}
                )
        click.echo("Users persisted in DynamoDB.")
    except Exception as e:
        click.secho(e)


def get_presigned_urls(config: object, users: list) -> list:
    """get presigned login URL for each user"""

    sm_client = boto3.client("sagemaker", config.region)

    users_to_urls = {}
    for user_email, team in users.items():
        username = getUsernameFromEmail(user_email)
        team = str(team)

        try:
            response = sm_client.create_presigned_domain_url(
                DomainId=config.domain_id,
                UserProfileName=username,
                SessionExpirationDurationInSeconds=43200,  # 3 days
                ExpiresInSeconds=300,  # 5 minutes
                SpaceName=team,
            )

            users_to_urls[user_email] = response["AuthorizedUrl"]

        except sm_client.exceptions.ResourceNotFound as e:
            click.secho(
                f"Could not create presigned url for user '{username}' and space '{team}'",
                fg="red",
            )
            click.secho(e, fg="red")

    return users_to_urls


def delete_users(config: object, user_emails: str) -> None:
    """Deletes all SageMaker user profiles"""

    sm_client = boto3.client("sagemaker", config.region)

    with click.progressbar(
        user_emails, label="Deleting SM user profiles"
    ) as users_emails:
        for email in users_emails:
            username = getUsernameFromEmail(email)
            try:
                sm_client.delete_user_profile(
                    DomainId=config.domain_id, UserProfileName=username
                )
            except sm_client.exceptions.ResourceNotFound:
                pass
            except Exception as e:
                click.error(e)


def delete_spaces(config: object) -> None:
    """Deletes all SageMaker spaces related to the Domain ID in the config file"""

    sm_client = boto3.client("sagemaker", config.region)

    response = sm_client.list_spaces(DomainIdEquals=config.domain_id)
    spaces = response["Spaces"]

    with click.progressbar(spaces, label="Deleting SM spaces") as space_list:
        for space in space_list:
            try:
                response = sm_client.delete_space(
                    DomainId=space["DomainId"], SpaceName=space["SpaceName"]
                )
            except sm_client.exceptions.ResourceInUse:
                click.echo(
                    f"\nCould not delete space because there's probably still an app that's pending deletion inside it. Try running this command (purge) again in a minute or two"
                )


def delete_apps(config: object) -> None:
    """Deletes all running Apps in the domain"""

    def delete_app(app):
        if app["Status"] == "Deleted":
            # App already deleted since before.
            return
        if app["Status"] == "Pending":
            click.secho(
                f"App type {app['AppType']} is already pending deletion", fg="red"
            )
            # Already pending deletion
            return
        if app["Status"] == "Deleting":
            click.secho(
                f"App type {app['AppType']} is in the process of deletion.", fg="red"
            )
            # Already pending deletion
            return

        try:
            sm_client.delete_app(
                DomainId=app["DomainId"],
                AppName=app["AppName"],
                AppType=app["AppType"],
                SpaceName=app["SpaceName"],
            )
            click.echo(f"Deleted app of type: {app['AppType']}")
        except sm_client.exceptions.ResourceInUse:
            click.secho("App currently in use... Can not delete right now.", fg="red")
        except Exception as e:
            click.secho(f"Error deleting app {app}: \n{str(e)}", fg="red")

    sm_client = boto3.client("sagemaker", config.region)

    response = sm_client.list_apps(DomainIdEquals=config.domain_id)
    apps = response["Apps"]

    # Parallelize the app deletion
    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(delete_app, apps)


def get_or_create_table(region: str) -> str:
    """Gets or creates a DDB table for keeping state

    Parameters:
        region (str): AWS Region to use

    Returns:
        str: Name of DDB table
    """

    ddb_client = boto3.client("dynamodb", region)

    try:
        response = ddb_client.list_tables()
        table_list = [i for i in response["TableNames"] if i.startswith("studio-cli-")]
        if table_list:
            table = table_list[0]
            click.echo(f"Found existing studio-cli table. \nUsing table: {table}")
        else:
            # Create table
            click.echo("No existing table for studio-cli. Creating...")
            table = f"studio-cli-{round(time.time())}"
            response = ddb_client.create_table(
                AttributeDefinitions=[
                    {"AttributeName": "pk", "AttributeType": "S"},
                ],
                TableName=table,
                KeySchema=[
                    {"AttributeName": "pk", "KeyType": "HASH"},
                ],
                BillingMode="PAY_PER_REQUEST",
                Tags=[
                    {"Key": "project", "Value": "studio-cli"},
                ],
            )
            click.echo(f"Created Table: {table}")

        return table

    except Exception as e:
        click.echo(e)


def get_users_from_ddb(config: object) -> object:
    """Gets all users from DDB"""
    dynamodb_resource = boto3.resource("dynamodb", config.region)
    table = dynamodb_resource.Table(config.table_name)

    # Perform a scan operation to get all items in the table
    response = table.scan()

    users = {}

    # Delete all items
    for item in response.get("Items", []):
        users[item["pk"]] = item["team"]

        # Continue scanning if there are more items
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        for item in response.get("Items", []):
            users[item["pk"]] = item["team"]

    return users


def clear_ddb(config: object) -> None:
    """Deletes all items in the configured DDB table"""

    dynamodb_resource = boto3.resource("dynamodb", config.region)
    table = dynamodb_resource.Table(config.table_name)

    click.echo("Clearing DDB table...")

    # Perform a scan operation to get all items in the table
    response = table.scan()

    # Delete all items
    with table.batch_writer() as batch:
        for item in response.get("Items", []):
            batch.delete_item(Key={"pk": item["pk"]})

        # Continue scanning if there are more items
        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            for item in response.get("Items", []):
                batch.delete_item(Key={"pk": item["pk"]})
