#!/usr/bin/env bash
#
# ssh-deploy-wrapper.sh -- forced command for the GitHub Actions deploy SSH key
#
# Installed as the `command=` restriction in
# /home/opencode/.ssh/authorized_keys for the deploy key's public key entry:
#
#   command="/home/opencode/thinkcode-deploy/ssh-deploy-wrapper.sh",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA...
#
# This means that key, even if leaked, can NEVER get an interactive shell or
# run arbitrary commands on the server -- SSH always runs THIS script
# instead of whatever the client asked for, and this script only accepts one
# very narrow request shape (see below). This is on top of the key already
# being scoped to a single low-privilege user (opencode) that can only
# docker-related things via group membership (see CI-CD.md).
#
# The real command the client wanted is available in $SSH_ORIGINAL_COMMAND.
# Expected format (set by .github/workflows/deploy.yml):
#
#   deploy <image-ref>
#
# The GHCR token is read from stdin (piped by the workflow), NOT passed as a
# command argument -- arguments are visible to any other process on the
# server via `ps aux` for the SSH session's lifetime and may end up in
# shell/audit logs, whereas stdin is not.
#
# Anything else is rejected.

set -euo pipefail

read -r action image <<< "${SSH_ORIGINAL_COMMAND:-}"

if [ "$action" != "deploy" ] || [ -z "$image" ]; then
    echo "Rejected: this key may only run 'deploy <image-ref>' (token via stdin)" >&2
    exit 1
fi

read -r token

# Basic sanity check on the image ref to avoid shell-injection-via-argument
# shenanigans further down the line (deploy.sh itself also treats it as an
# opaque docker image reference, never eval'd).
if [[ ! "$image" =~ ^ghcr\.io/[a-z0-9._-]+/[a-z0-9._-]+:[a-zA-Z0-9._-]+$ ]]; then
    echo "Rejected: image ref does not look like a valid ghcr.io reference: ${image}" >&2
    exit 1
fi

echo "$token" | docker login ghcr.io -u x-access-token --password-stdin

exec /home/opencode/thinkcode-deploy/deploy.sh "$image"
