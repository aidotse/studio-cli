import boto3
import botocore
import click
import time
import re
import sys
import threading

from concurrent.futures import ThreadPoolExecutor


def get_username_from_email(email: str) -> str:
    """Gets username from email

    Parameters:
        email (str): an email adress

    Returns:
        str: username
    """
    username = re.sub(r"[^a-zA-Z0-9]+", "", email.split("@")[0])

    return username


def get_jupyter_space_name(username: str) -> str:
    """Gets space name from username

    Parameters:
        user (str): username

    Returns:
        str: space name
    """
    space_name = f"{username}-jupyter-space"

    return space_name


def get_code_editor_space_name(username: str) -> str:
    """Gets space name from username

    Parameters:
        user (str): username

    Returns:
        str: space name
    """
    space_name = f"{username}-ce-space"

    return space_name


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
            username = get_username_from_email(user_email)
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

                except sm_client.exceptions.ResourceLimitExceeded:
                    click.secho(
                        f'You have reached the maximum allowed SageMaker users! You need to submit a quota increase request: "Maximum number of Studio user profiles allowed per account"',
                        fg="red",
                    )
                    sys.exit(1)

                except:
                    click.secho(
                        f"User with name '{user_email}' could not be created for some reason. Skipping",
                        fg="red",
                    )
    return


def create_sagemaker_spaces(config: object, users_email_list: list) -> None:
    """Create SageMaker Studio Domain spaces for each user in the users_email_list

    Parameters:
        config (object): CLI configuration object.
        users_email_list (list): List of user emails
    Returns:
        None
    """

    sm_client = boto3.client("sagemaker", config.region)

    with click.progressbar(
        users_email_list, label="Creating stopped instances for notebooks and editors"
    ) as user_emails:
        for user_email in user_emails:
            username = get_username_from_email(user_email)
            jupyter_space_name = get_jupyter_space_name(username)
            ce_space_name = get_code_editor_space_name(username)
            try:
                sm_client.describe_space(
                    DomainId=config.domain_id, SpaceName=jupyter_space_name
                )
            except sm_client.exceptions.ResourceNotFound:
                # Space does not exist. Create space
                try:
                    sm_client.create_space(
                        DomainId=config.domain_id,
                        SpaceName=jupyter_space_name,
                        OwnershipSettings={"OwnerUserProfileName": username},
                        SpaceSettings={"AppType": "JupyterLab"},
                        SpaceSharingSettings={"SharingType": "Private"},
                    )

                    sm_client.create_space(
                        DomainId=config.domain_id,
                        SpaceName=ce_space_name,
                        OwnershipSettings={"OwnerUserProfileName": username},
                        SpaceSettings={"AppType": "CodeEditor"},
                        SpaceSharingSettings={"SharingType": "Private"},
                    )
                except sm_client.exceptions.ResourceLimitExceeded:
                    click.secho(
                        f"\nYou have reached the maximum allowed SageMaker spaces! You need to submit a quota increase request!",
                        fg="red",
                    )
                    sys.exit(1)
                    return False

                except Exception as e:
                    click.secho(
                        f"Space with name '{username}' could not be created for some reason. Skipping\n\n {str(e)}",
                        fg="red",
                    )

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
        username = get_username_from_email(user_email)
        # space_name = get_jupyter_space_name(username)

        try:
            response = sm_client.create_presigned_domain_url(
                DomainId=config.domain_id,
                UserProfileName=username,
                SessionExpirationDurationInSeconds=43200,  # 3 days
                ExpiresInSeconds=300,  # 5 minutes
                # SpaceName=space_name,
                # LandingUri="app:JupyterLab:",
            )

            users_to_urls[user_email] = response["AuthorizedUrl"]

        except sm_client.exceptions.ResourceNotFound as e:
            click.secho(
                f"Could not create presigned url for user '{username}' and space '{team}'",
                fg="red",
            )
            click.secho(e, fg="red")

    return users_to_urls


def delete_users(config: object) -> bool:
    """Deletes all SageMaker user profiles"""
    click.echo("\n** Deleting SageMaker user profiles... **")

    sm_client = boto3.client("sagemaker", config.region)

    def delete_user(user_profile: str, time_to_wait=2) -> None:
        """Deletes one user with retry"""

        user_profile_name = user_profile["UserProfileName"]

        try:
            response = sm_client.describe_user_profile(
                DomainId=config.domain_id, UserProfileName=user_profile_name
            )

            if response["Status"] in ["Update_Failed", "Delete_Failed", "Failed"]:
                # Something went wrong!
                if time_to_wait > 11:
                    click.secho(
                        f"User has been attempting deleteion for a long time. Waiting again for {time_to_wait} seconds",
                        fg="red",
                    )
                    return False

                click.echo(f"Deleting user {user_profile_name} has failed. Retrying...")

                time.sleep(time_to_wait)

                return delete_user(user_profile, time_to_wait * 1.5)

            if response["Status"] in ["Deleting", "Pending", "Updating"]:
                # Some action is already pending
                click.echo(
                    f"User {user_profile_name} is pending som action. Retrying..."
                )

                if time_to_wait > 11:
                    click.secho(
                        f"User has been attempting deleteion for a long time. Waiting again for {time_to_wait} seconds",
                        fg="red",
                    )
                    return False

                time.sleep(time_to_wait)

                return delete_user(user_profile, time_to_wait * 1.5)

            else:
                # Status is InService
                try:
                    sm_client.delete_user_profile(
                        DomainId=config.domain_id, UserProfileName=user_profile_name
                    )

                except sm_client.exceptions.ResourceInUse:
                    # Some resournce the user is associated with is most likely in use. Retrying
                    if time_to_wait > 11:
                        click.secho(
                            f"User {user_profile_name} is in active use. Try again later when their session has expired.",
                            fg="red",
                        )
                        return False

                    click.echo(f"User {user_profile_name} is in use. Retrying...")
                    return delete_user(user_profile, time_to_wait * 1.5)

                except sm_client.exceptions.ResourceNotFound:
                    return True

                except botocore.exceptions.ClientError as e:
                    if e.response["Error"]["Code"] == "ThrottlingException":
                        # Throttling Exception occurred

                        click.secho(
                            "There's some throttling exceptions... Calming down a bit.",
                            fg="yellow",
                        )
                        time.sleep(5)
                        return delete_user(user_profile, time_to_wait)
                    else:
                        click.secho(f"Unhandled error occured:\n {e}", fg="red")
                        return False

                except Exception as e:
                    click.secho(
                        f"Something went wrong when deleting user {user_profile_name}. {str(e)}",
                        fg="red",
                    )
                    return False

        except sm_client.exceptions.ResourceNotFound:
            # User does not exist
            return True

        except sm_client.exceptions.ResourceLimitExceeded as e:
            click.secho(f"Some resource limit have been exceeded! \n {e}", fg="red")
            sys.exit(1)

    user_profiles = []
    next_token = None

    while True:
        params = {"DomainIdEquals": config.domain_id}
        if next_token:
            params["NextToken"] = next_token

        response = sm_client.list_user_profiles(**params)
        user_profiles.extend(response["UserProfiles"])

        next_token = response.get("NextToken")
        if not next_token:
            break

    # Parallelize the app deletion
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(delete_user, user_profiles)

    deleted_all_users = all(results)

    if deleted_all_users:
        click.echo("All users deleted successfully.")
    else:
        click.secho(
            "Not all users were deleted successfully. Try again in a few minutes.",
            fg="red",
        )

    return deleted_all_users


def delete_spaces(config: object) -> bool:
    """Deletes all SageMaker spaces related to the Domain ID in the config file"""

    click.echo("\n** Deleting all spaces in the domain... **")

    sm_client = boto3.client("sagemaker", config.region)

    def delete_space(space: object, time_to_wait=2):
        """Deletes a space with retry and waiting"""

        try:
            space = sm_client.describe_space(
                DomainId=space["DomainId"], SpaceName=space["SpaceName"]
            )

            space_name = space["SpaceName"]

            if space["Status"] in [
                "Update_Failed",
                "Delete_Failed",
                "Failed",
            ]:
                # Something went wrong!
                click.secho(
                    f"Something went wrong when deleting space: \n{space}", fg="red"
                )
                return False

            if space["Status"] in ["Deleting", "Pending", "Updating"]:
                # Space is still deleting.
                click.echo(f"Space {space_name} is pending deletion")

                if time_to_wait > 15:
                    click.secho(
                        f"Space {space_name} couldn't be deleted... Try again in a few minutes.",
                        fg="red",
                    )
                    return False

                time.sleep(time_to_wait)
                return delete_space(space, time_to_wait * 1.5)

            else:
                # Status is in InService
                try:
                    sm_client.delete_space(
                        DomainId=space["DomainId"], SpaceName=space_name
                    )

                    return delete_space(space, time_to_wait * 1.5)

                except sm_client.exceptions.ResourceInUse:
                    # Space still in use.
                    click.secho(
                        f"Failed to delete Space. Space still in use: \n{space}",
                        fg="red",
                    )
                    return False

                except sm_client.exceptions.ResourceNotFound:
                    # Space already deleted.
                    return True

                except botocore.exceptions.ClientError as e:
                    if e.response["Error"]["Code"] == "ThrottlingException":
                        # Throttling Exception occurred

                        click.secho(
                            "There's some throttling exceptions... Calming down a bit.",
                            fg="yellow",
                        )
                        time.sleep(5)
                        return delete_space(space, time_to_wait)
                    else:
                        click.secho(f"Unhandled error occured:\n {e}", fg="red")
                        return False

        except sm_client.exceptions.ResourceNotFound:
            # Space already deleted.
            return True

    spaces = []
    next_token = None

    while True:
        params = {"DomainIdEquals": config.domain_id}
        if next_token:
            params["NextToken"] = next_token

        response = sm_client.list_spaces(**params)
        spaces.extend(response["Spaces"])

        next_token = response.get("NextToken")
        if not next_token:
            break

    # Parallelize the app deletion
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(delete_space, spaces)

    deleted_all_spaces = all(results)

    if deleted_all_spaces:
        click.echo("All spaces deleted successfully.")
    else:
        click.secho(
            "Not all spaces were deleted successfully. Try again in a few minutes.",
            fg="red",
        )

    return deleted_all_spaces


def delete_apps(config: object) -> bool:
    """Deletes all running Apps in the domain"""
    click.echo(
        "\n** Stopping all running apps (Notebooks/Code Editors) in the domain... **"
    )

    sm_client = boto3.client("sagemaker", config.region)

    def delete_app(app, time_to_wait=2):
        app_name = app["AppName"]
        app_type = app["AppType"]
        space_name = app["SpaceName"]

        try:
            # describe app
            response = sm_client.describe_app(
                DomainId=config.domain_id,
                AppName=app_name,
                AppType=app_type,
                SpaceName=space_name,
            )

            if response["Status"] in ["Pending", "Deleting"]:
                click.echo(
                    f"app {app_name} in space {space_name} is pending deletion..."
                )

                # Delete or update in progress
                time.sleep(time_to_wait)
                return delete_app(app, time_to_wait * 1.5)

            if response["Status"] in ["Deleted"]:
                return True

            if response["Status"] in ["Failed"]:
                # Something went wrong!
                click.secho(
                    f"Something went wrong when deleting app: \n{response}", fg="red"
                )
                return False

            try:
                # Status is InService - Delete app
                sm_client.delete_app(
                    DomainId=config.domain_id,
                    AppName=app_name,
                    AppType=app_type,
                    SpaceName=app["SpaceName"],
                )

                time.sleep(time_to_wait)
                return delete_app(app, time_to_wait)

            except sm_client.exceptions.ResourceInUse:
                # In use. Wait and retry

                if time_to_wait > 15:
                    click.secho(
                        f"AppType: {app_type} in space {space_name} couldn't be deleted... Try again in a few minutes.",
                        fg="red",
                    )

                    return False

                time.sleep(time_to_wait)

                return delete_app(app, time_to_wait * 1.5)

            except sm_client.exceptions.ResourceNotFound:
                # Does not exist
                return True

            except botocore.exceptions.ClientError as e:
                if e.response["Error"]["Code"] == "ThrottlingException":
                    # Throttling Exception occurred

                    click.secho(
                        "There's some throttling exceptions... Calming down a bit.",
                        fg="yellow",
                    )
                    time.sleep(5)
                    return delete_app(app)
                else:
                    click.secho(f"Unhandled error occured:\n {e}", fg="red")
                    return False

        except sm_client.exceptions.ResourceNotFound:
            # App does not exist
            return True

    apps = []
    next_token = None

    while True:
        params = {"DomainIdEquals": config.domain_id}
        if next_token:
            params["NextToken"] = next_token

        response = sm_client.list_apps(**params)
        apps.extend(response["Apps"])

        next_token = response.get("NextToken")
        if not next_token:
            break

    # Parallelize the app deletion
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(delete_app, apps)

    deleted_all_apps = all(results)

    if deleted_all_apps:
        click.echo("All apps deleted successfully.")
    else:
        click.secho(
            "Not all apps were deleted successfully. Try again in a few minutes.",
            fg="red",
        )

    return deleted_all_apps


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

    click.echo("\n**Clearing DDB table... **")

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
