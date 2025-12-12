FROM python:3.12-slim

# Install git (required for diffing)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install the package dependencies
# We copy everything to install the tool itself
COPY . .
RUN pip install .

# Make sure we trust the workspace directory (safe for CI)
RUN git config --global --add safe.directory /github/workspace

# The entrypoint is the jnkn CLI
ENTRYPOINT ["jnkn"]