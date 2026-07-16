FROM mcr.microsoft.com/devcontainers/python:1-3.11-bookworm

# Yarn is unused here; drop the inherited apt source so its key cannot break builds.
RUN rm -f /etc/apt/sources.list.d/yarn.list \
        /etc/apt/sources.list.d/yarn.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL \
        -o /tmp/google-cloud-apt-key.gpg \
        https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    && gpg --dearmor \
        --output /usr/share/keyrings/google-cloud.gpg \
        /tmp/google-cloud-apt-key.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/google-cloud.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
        > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-cloud-cli \
    && rm -rf /var/lib/apt/lists/* /tmp/google-cloud-apt-key.gpg
