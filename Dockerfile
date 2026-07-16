ARG FUNCTION_DIR="/home/app/"
ARG RUNTIME_VERSION="3.11"

FROM python:3.11-slim-bookworm as dev-image

RUN apt update && apt install -y \
    curl git ca-certificates gnupg sudo \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg add - \
    && apt update && apt install -y \
    google-cloud-cli \
    && apt clean \
    && rm -rf /var/lib/apt/lists/*

#COPY src/requirements.txt .
#RUN pip install --user -r requirements.txt
#RUN curl -sL https://firebase.tools | bash

#FROM python:3.11-slim-bullseye as deploy-image
#COPY --from=dev-image /root/.local /root/.local
#RUN apt-get update && apt-get install -y \
#    curl git ca-certificates \
#    && apt-get clean \
#    && rm -rf /var/lib/apt/lists/*
