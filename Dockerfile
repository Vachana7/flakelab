FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/Vachana7/flakelab"
LABEL org.opencontainers.image.description="PipeDelta: report what new powers a change gives a GitHub Actions pipeline"

# git is needed to read the old and new versions of each workflow file.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/pipedelta
COPY pyproject.toml README.md ./
COPY pipedelta ./pipedelta
RUN pip install --no-cache-dir .

# GitHub mounts the repository with a different owner than the container
# user, and git refuses to read it unless the folder is marked as safe.
RUN git config --system --add safe.directory '*'

# Do not run as root.
RUN useradd --create-home runner
USER runner

ENTRYPOINT ["pipedelta"]
