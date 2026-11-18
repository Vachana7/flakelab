FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/Vachana7/pipedelta"
LABEL org.opencontainers.image.description="PipeDelta: report what new powers a change gives a GitHub Actions pipeline"

# git is needed to read the old and new versions of each workflow file.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/pipedelta
COPY pyproject.toml README.md ./
COPY pipedelta ./pipedelta
# zizmor is the optional second opinion (--zizmor on). Its version is fixed so
# results do not change between runs.
RUN pip install --no-cache-dir . zizmor==1.32.0

# GitHub mounts the repository with a different owner than the container
# user, and git refuses to read it unless the folder is marked as safe.
RUN git config --system --add safe.directory '*'

# The container runs as root because GitHub requires that for Docker actions:
# the files it hands to the container (step summary, outputs) are otherwise
# not writable. PipeDelta only reads the repository and never runs its code.

ENTRYPOINT ["pipedelta"]
