# Studio CLI

A small light-weight cli to manage users and teams for hackathons using SageMaker Studio Spaces

## Prerequisites

- A SageMaker Studio Studio Domain created, with IAM (**not Identity Center**) to manage access.
- Active AWS credentials in the current environment in the same account as the SageMaker Studio domain

## Installation

You can install the CLI using pip, or use Docker to use the CLI in a containerized environment

### Using pip

In the root of the directory, run

```bash
pip install .
```

### Using Docker (Optional)

For convenience, and to avoid installing the CLI/Python dependencies on your machine you can optionally use Docker to run the CLI.

```bash
docker build . -t studio-cli # Build the Docker image and tag it as "studio-cli"
docker run -it --rm studio-cli # Run the CLI in a container (and remove the container when exiting)
```

This will launch an interactive shell inside the Docker container with the CLI pre-installed. From there you can run any of the CLI commands as documented below.

## Example usage

Here's how to use some of the more useful commands

### Configure the CLI

```bash
studio configure
```

Persists the configuration, including region, Studio domain ID and DDB table name.

### Show current configuration

```bash
studio get-conf
```

### Configure the CLI

```bash
studio configure
```

### Setup users and teams

```bash
studio setup-users users.csv
```

where users.csv is a csv with 2 columns, an email and a team number. See sample.

Run this when

- you have all participants and team divisions before an event, to create SM user profiles and SM team spaces.

### Get presigned URLs

```bash
studio get-urls
```

Run this when

- you want to generate presigned URLs (valid for 5 minutes) to distribute to hackathon participants.
  > Note: This is not necessary if you use the web-app

### Finish an event

```bash
studio purge
```

Tries to delete all hackathon-related resources.

Run this when

- The event is over to delete all SM user profiles and SM spaces and apps.

### Issues

> Purge: The purge command tries to use the API to delete all related resources. There are a lot fo dependencies between the different resources, meaning that some resources can't be deleted untill others are. i.e a space cannot be deleted untill all apps runnning in that space have been deleted. To avoid having a command running for 30 minutes, some resource deleteions are skipped in case there are deletions in progress for resources it's depending on. This mean that the purge command may have to be run several times, preferably with some time in between.

> Same Email: SM user profiles are created based on the email. If users share the first part of the email, i.e niklas@amazon.com and niklas@ai.se, the last occuring person in the list will not get a user profile created. This is known issue with the current implementation.

### Limits

These are some, but not an extensive list of AWS service limits you need to be mindful of.

- Allowed studio profiles per SM Domain. (This maps to the number of participants)
- Maximum number of Studio spaces allowed per account. (This maps to the number of teams)
- Studio KernelGateway Apps running on <Instance type> instance. (These are the underlying instances. Note that the ml instances are different to the EC2 instances, with different qoutas.)
- Max number of running studio Apps (Each team has a **minimum** of 2, but probably more depending on what underlying Image they run on their instances.)

### Web App

If you want hackathon participants to have a lightweigh web app where they can enter their email and get redirected to their teams SageMaker Studio Space, follow the instructions in [web-app/README.md](web-app/README.md)
