FROM python:3.12-slim

# Install git (required for diffing)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install the package dependencies
COPY . .
RUN pip install .

# Make sure we trust the workspace directory (safe for CI)
RUN git config --global --add safe.directory /github/workspace

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Use entrypoint script instead of jnkn directly
ENTRYPOINT ["/entrypoint.sh"]
