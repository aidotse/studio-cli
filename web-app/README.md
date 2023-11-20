# Studio CLI frontend

This sets up a small backend and hosting for a frontend to let hackathon participants access their SageMaker Studio domain users in a self-service fashion.

## Prerequisites

- Studio CLI installed
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) installed
- NodeJS installed
- Active AWS credentials in you environment.

## Installation

### Backend

Start by setting up the website hosting and the Lambda-backed API.

In the `backend`directory, after injecting the region you've configured in the Studio-CLI, run

```bash
sam build && sam deploy \
            --stack-name studio-cli-frontend \
            --resolve-s3 \
            --region <WHAT REGION?> \
            --no-fail-on-empty-changeset \
            --no-confirm-changeset \
            --capabilities CAPABILITY_IAM \
            --tags project=hackathon
```

This takes a few minutes due to a CloudFront distribution being set up to front the hosting bucket. If you have a different python version installed, or experience errors with the build command, run the build inside a container `sam build --use-container`

Take note of the outputs from deployment:

- Name of hosting bucket
- GetUrlAPI domain name
- Cloudfront domain name

You'll use these when setting up the frontend in the next step

### Frontend

After the backend has completed deploying, change the `API_URL` placeholder in `frontend/src/utils/helper.js` to the `GetUrlAPI` in the output from the backend deployment step.

Then, in the `frontend`` directory, run

```bash
npm install && npm run build && aws s3 cp build/ s3://<HOSTING-BUCKET-NAME>/ --recursive
```

replacing the `<HOSTING-BUCKET-NAME>` with the name of the hosting bucket in output of the backend deployment step. This copies the React build artefact to the S3 bucket fronted by the CloudFront distribution.

### Usage

Once you've completed the 2 deployments steps above, you should be able to access the frontend at the cloudfront domain name which was outputed in the backend deployment step.

> Nota Bene - This is not a production-ready product and all usage is at your own risk. Corners have been cut, both in terms of code quality and permission boundaries.

> Note Bene - The API that's created does not contain any authentication.
