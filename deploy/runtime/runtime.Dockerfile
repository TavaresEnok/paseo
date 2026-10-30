FROM golang:1.27.3-alpine AS go_toolchain
FROM node:22.23.4-alpine AS node_tools
FROM python:3.11-slim-bookworm
COPY paseo-compat /usr/local/bin/paseo-compat
SHELL ["/usr/local/bin/paseo-compat", "/bin/sh", "-c"]
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && apt-get -o Acquire::Retries=1 -o Acquire::https::Timeout=25 update && apt-get install -y --no-install-recommends bash git ca-certificates curl procps libstdc++6 gcc libc6-dev && rm -rf /var/lib/apt/lists/* && ln -s /usr/local/bin/python3 /usr/bin/python3
COPY --from=go_toolchain /usr/local/go /usr/local/go
COPY --from=node_tools /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx && ln -s /usr/local/lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack
ENV PATH="/usr/local/go/bin:${PATH}"
LABEL paseo.orchestrator.runtime="true"

ENTRYPOINT ["/usr/local/bin/paseo-compat"]

RUN groupadd -g 1000 paseo && useradd -u 1000 -g 1000 -m -s /bin/bash enok
