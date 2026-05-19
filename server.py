#!/usr/bin/env python3

import os
import json
import glob
import configparser
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

import boto3


def load_profile_config(profile_name):
    """Load SSO settings from ~/.aws/config for the given profile."""
    config = configparser.ConfigParser()
    config.read(os.path.expanduser("~/.aws/config"))

    section = f"profile {profile_name}" if profile_name != "default" else "default"
    if not config.has_section(section):
        raise RuntimeError(f"Profile '{profile_name}' not found in ~/.aws/config")

    required = ["sso_start_url", "sso_account_id", "sso_role_name"]
    missing = [k for k in required if not config.has_option(section, k)]
    if missing:
        raise RuntimeError(f"Profile '{profile_name}' missing: {', '.join(missing)}")

    return {
        "sso_start_url": config.get(section, "sso_start_url"),
        "sso_region": config.get(section, "sso_region", fallback="us-east-1"),
        "sso_account_id": config.get(section, "sso_account_id"),
        "sso_role_name": config.get(section, "sso_role_name"),
    }


def find_sso_token(sso_start_url):
    """Find a valid SSO access token from the cache."""
    cache_dir = os.path.expanduser("~/.aws/sso/cache")
    for path in glob.glob(os.path.join(cache_dir, "*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
            if data.get("startUrl") != sso_start_url:
                continue
            expires = datetime.fromisoformat(data["expiresAt"].replace("Z", "+00:00"))
            if expires > datetime.now(timezone.utc):
                return data["accessToken"]
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return None


def get_sso_credentials(sso_start_url, sso_region, account_id, role_name):
    """Get role credentials using the cached SSO token."""
    token = find_sso_token(sso_start_url)
    if not token:
        raise RuntimeError("No valid SSO token found. Run: aws sso login --profile <profile>")

    client = boto3.client("sso", region_name=sso_region)
    resp = client.get_role_credentials(
        roleName=role_name,
        accountId=account_id,
        accessToken=token,
    )
    creds = resp["roleCredentials"]
    expiration = datetime.fromtimestamp(creds["expiration"] / 1000, tz=timezone.utc)
    return {
        "AccessKeyId": creds["accessKeyId"],
        "SecretAccessKey": creds["secretAccessKey"],
        "Token": creds["sessionToken"],
        "Expiration": expiration.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Code": "Success",
        "Message": "",
    }


# Load profile config once at startup
PROFILE = os.environ.get("AWS_PROFILE", "default")
CONFIG = load_profile_config(PROFILE)
print(f"Loaded profile '{PROFILE}': account={CONFIG['sso_account_id']}, role={CONFIG['sso_role_name']}")


class CredentialsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if urlparse(self.path).path == "/credentials":
            self.handle_credentials()
        else:
            self.send_error(404, "Not Found")

    def handle_credentials(self):
        try:
            response_data = get_sso_credentials(
                sso_start_url=CONFIG["sso_start_url"],
                sso_region=CONFIG["sso_region"],
                account_id=CONFIG["sso_account_id"],
                role_name=CONFIG["sso_role_name"],
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())
        except Exception as e:
            print(f"Error: {e}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"Code": "Error", "Message": str(e)}).encode())

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")


def run_server():
    port = int(os.environ.get("CREDENTIALS_PROXY_PORT", "8000"))
    httpd = HTTPServer(("0.0.0.0", port), CredentialsHandler)
    print(f"SSO credential proxy listening on port {port}")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()
