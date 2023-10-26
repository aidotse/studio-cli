import json
import re
import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.logging import correlation_paths

logger = Logger()

ddb_client = boto3.client("dynamodb")
dynamodb_resource = boto3.resource("dynamodb")
sm_client = boto3.client("sagemaker")

table = ""

# Check that there's a table starting with studio-cli-. If not, event is not initialized
response = ddb_client.list_tables()
table_list = [i for i in response["TableNames"] if i.startswith("studio-cli-")]
if table_list:
    table = table_list[0]


def getUsernameFromEmail(email: str) -> str:
    """Gets username from email

    Parameters:
        email (str): an email adress

    Returns:
        str: username
    """
    username = re.sub(r"[^a-zA-Z0-9]+", "", email.split("@")[0])

    return username


def get_response_body(message, presigned=""):
    """Return stringified response body object

    Parameters:
        message (str): Message to be sent back to the client, and displayed in the browser.

        presigned (str): (optional) Presigned URL

    Returns:
        str: Stringified dict with message and potentially the presigned URL
    """

    if presigned:
        return json.dumps({"message": message, "presigned": presigned})

    return json.dumps({"message": message})


@logger.inject_lambda_context(
    correlation_id_path=correlation_paths.API_GATEWAY_REST, log_event=True
)
def lambda_handler(event, context):
    response_headers = {
        "Access-Control-Allow-Origin": "*",
    }

    if not table:
        logger.error("No DDB table was found")
        return {
            "statusCode": 404,
            "headers": response_headers,
            "body": get_response_body(
                "There's no table holding the state of the hackathon! Verify that you've run the setup-users command with studio-cli"
            ),
        }

    body = event["body"]
    logger.info(body)

    if "email" not in body:
        logger.error("No email in body")
        return {
            "statusCode": 400,
            "headers": response_headers,
            "body": get_response_body("There's no email in the body"),
        }

    body = json.loads(body)

    ddb_table = dynamodb_resource.Table(table)
    response = ddb_table.get_item(Key={"pk": body["email"]})

    if "Item" not in response:
        # user is not in DDB
        return {
            "statusCode": 404,
            "headers": response_headers,
            "body": get_response_body(
                "This email is not registered with the event, or the event is over"
            ),
        }

    logger.info(response)

    user_item = response["Item"]

    username = getUsernameFromEmail(user_item["pk"])
    team = user_item["team"]
    domain_id = user_item["domain-id"]

    try:
        response = sm_client.create_presigned_domain_url(
            DomainId=domain_id,
            UserProfileName=username,
            SessionExpirationDurationInSeconds=43200,  # 3 days
            ExpiresInSeconds=300,  # 5 minutes
            SpaceName=team,
        )

        presigned = response["AuthorizedUrl"]

    except sm_client.exceptions.ResourceNotFound as e:
        logger.error(e)
        return {
            "statusCode": 500,
            "headers": response_headers,
            "body": get_response_body(
                "Something went wrong trying to generate presigned URL"
            ),
        }

    return {
        "statusCode": 200,
        "headers": response_headers,
        "body": get_response_body("ok", presigned),
    }
