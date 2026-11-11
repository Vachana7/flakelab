# FlakeLab image: the FlakeLab CLI plus the Docker command-line client.
#
# FlakeLab does not run tests inside its own container. It asks the HOST's Docker
# engine (through the mounted /var/run/docker.sock) to start a fresh container
# for every experiment run. This is often called "Docker-out-of-Docker".
#
# Security note: access to the Docker socket is equivalent to root access on the
# host. Only run this image on machines you control (your laptop, a CI runner).
FROM docker:27-cli AS docker-cli

FROM python:3.12-slim
LABEL org.opencontainers.image.title="FlakeLab" \
      org.opencontainers.image.description="Experimental root-cause investigation for unreliable CI tests" \
      org.opencontainers.image.licenses="MIT"

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /opt/flakelab
COPY pyproject.toml README.md ./
COPY flakelab ./flakelab
RUN pip install --no-cache-dir . && flakelab --version

ENTRYPOINT ["flakelab"]
CMD ["--help"]
