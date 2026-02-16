FROM --platform=${BUILDPLATFORM} ubuntu:24.04 AS zwave-ts-dev

ARG DEBIAN_FRONTEND=noninteractive

USER root

# Remove default ubuntu user and create zwave user (similar to z-wave repo)
RUN userdel -r ubuntu || true \
  && groupadd -g 1000 zwave \
  && useradd -l -c "Zwave TS user" -d /home/zwave -u 1000 -g 1000 -m zwave \
  && usermod --shell /bin/bash zwave

ENV TZ=Etc/UTC
ENV LANG=C.UTF-8

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    bash-completion \
    build-essential \
    ca-certificates \
    curl \
    git \
    git-lfs \
    libboost-log-dev \
    libgl1 \
    libglib2.0-0 \
    libmosquitto-dev \
    mosquitto \
    mosquitto-clients \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    socat \
    ssh \
    sudo \
    unzip \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN echo "zwave ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Install CA certificates for corporate proxy/Vault
RUN mkdir -p /usr/share/ca-certificates/vault /usr/share/ca-certificates/pkicorp \
    && curl --insecure https://vault.silabs.net:443/v1/pki/ca/pem > /usr/share/ca-certificates/vault/vault-ca-prod.crt \
    && echo "vault/vault-ca-prod.crt" >> /etc/ca-certificates.conf \
    && curl --insecure --fail --show-error https://pkicorp.silabs.com/certdata/SL%20Root%20CA.crt \
    -o /usr/share/ca-certificates/pkicorp/sl-root-ca.crt \
    && echo "pkicorp/sl-root-ca.crt" >> /etc/ca-certificates.conf \
    && update-ca-certificates || true

RUN mkdir -p /opt/silabs \
    && chown -R zwave:zwave /opt/silabs \
    && curl https://artifactory.silabs.net/artifactory/zwave-gen/zwave-smoke-tests/uic-x68_64-ver_1.6.0-unstable-66-gc5a4e9119.zip > /opt/silabs/uic-x68_64-ver_1.6.0-unstable-66-gc5a4e9119.zip \
    && unzip /opt/silabs/uic-x68_64-ver_1.6.0-unstable-66-gc5a4e9119.zip -d /opt/silabs/uic \
    && rm /opt/silabs/uic-x68_64-ver_1.6.0-unstable-66-gc5a4e9119.zip \
    && chmod -R 777 /opt/silabs \
    && ln -s /opt/silabs/uic/uic/libunify.so /usr/lib

USER zwave
WORKDIR /home/zwave

# Prepare directory for user-specific binaries
RUN mkdir -p /home/zwave/.local/bin /home/zwave/.local/lib

# Avoid externally-managed-environment errors when using pip install
RUN python3 -m pip config set global.break-system-packages true

# Install Python dependencies (pytest and other basic requirements)
RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install pytest paho-mqtt setuptools
