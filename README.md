# Credential Provider — AWS SSO

A containerized AWS credential provider that reads credentials from your local `aws sso login` session and serves them via an ECS-compatible HTTP endpoint.

## How It Works

```
┌─────────────────┐    HTTP Request     ┌──────────────────┐    Read Cache     ┌─────────────────┐
│   Application   │ ──────────────────► │ Credential Proxy │ ────────────────► │ ~/.aws/sso/cache │
│   Container     │                     │   (Python/boto3) │                   │  (mounted r/o)   │
└─────────────────┘ ◄────────────────── └──────────────────┘ ◄──────────────── └─────────────────┘
                     JSON Credentials                          SSO Role Creds
```

1. You run `aws sso login --profile <profile>` on your host machine
2. The container reads your `~/.aws/config` to get SSO settings for the profile
3. It reads the cached SSO token from `~/.aws/sso/cache/` (mounted read-only)
4. It calls the AWS SSO `GetRoleCredentials` API to get temporary credentials
5. Serves them at `GET /credentials` in ECS credential provider format

## Prerequisites

- Docker and Docker Compose
- AWS CLI v2 configured with an SSO profile
- A valid SSO session (`aws sso login`)

## Setup

1. Configure an AWS SSO profile in `~/.aws/config`:

   ```ini
   [profile my-sso-profile]
   sso_start_url = https://my-org.awsapps.com/start
   sso_region = us-east-1
   sso_account_id = 123456789012
   sso_role_name = AdministratorAccess
   region = us-east-1
   ```

2. Login:

   ```bash
   aws sso login --profile my-sso-profile
   ```

3. Start the credential provider:

   ```bash
   cd credentials_provider_sso
   AWS_PROFILE=my-sso-profile docker compose up -d
   ```

## Using in Target Containers

```bash
docker run \
  --network credentials_provider_network \
  -e AWS_CONTAINER_CREDENTIALS_FULL_URI=http://169.254.170.2:8000/credentials \
  <your-container>
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_PROFILE` | AWS profile name to read SSO config from | `default` |
| `CREDENTIALS_PROXY_PORT` | HTTP server port | `8000` |

## Token Refresh

The SSO token typically lasts 8 hours. When it expires, re-run:

```bash
aws sso login --profile my-sso-profile
```

The container will automatically pick up the new token on the next request (the cache directory is mounted live).
