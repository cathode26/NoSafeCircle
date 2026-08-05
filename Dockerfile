FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        jq \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash agent

USER agent

ENV HOME=/home/agent
ENV PATH="/home/agent/.local/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

RUN curl -fsSL https://claude.ai/install.sh | bash

RUN git config --global --add safe.directory /workspace

WORKDIR /workspace

CMD ["bash"]
