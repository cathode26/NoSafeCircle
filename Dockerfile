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

# Keep Claude available for the existing course/pipeline tooling.
RUN curl -fsSL https://claude.ai/install.sh | bash

# Install OpenAI Codex CLI alongside Claude. Codex can authenticate with the
# user's ChatGPT account, so the new architecture review can run through Codex
# without requiring an OpenAI API key.
RUN curl -fsSL https://chatgpt.com/codex/install.sh | sh

RUN git config --global --add safe.directory /workspace

WORKDIR /workspace

CMD ["bash"]
