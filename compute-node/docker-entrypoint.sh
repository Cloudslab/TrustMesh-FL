#!/bin/bash
set -e

# Write daemon config before starting dockerd — storage-driver can only be set at startup, not via SIGHUP
echo '{"insecure-registries": ["sawtooth-registry:5000"], "storage-driver": "vfs"}' > /etc/docker/daemon.json

# Start the Docker daemon
dockerd &

# Wait for the Docker daemon to start
while ! docker info >/dev/null 2>&1; do
    echo "Waiting for Docker daemon to start..."
    sleep 1
done

# Run node_startup_script.py if IS_NEW_ADDITION is true
if [ "$IS_NEW_ADDITION" = "true" ]; then
    echo "Running node startup script..."
    python /app/node_startup_script.py
fi

# Execute the main command
exec "$@"