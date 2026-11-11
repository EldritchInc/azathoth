# syntax=docker/dockerfile:1

# Azathoth's container image (ADR 0101), with its MCP server (ADR 0111).
#
#   docker build -t azathoth .
#   docker run --rm azathoth --version
#   docker run --rm --entrypoint /usr/bin/tini azathoth -- azathoth-mcp --version

#
# Build both wheels from the checkout. Both stages start from the same base,
# pinned by digest, so a rebuild of a release uses exactly the base it was
# tested with. Dependabot proposes each new digest of the tag as a pull
# request, in both lines (ADR 0109).
#
FROM python:3.13-slim-trixie@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1 AS builder

WORKDIR /src

RUN python -m pip install --no-cache-dir --root-user-action=ignore build

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY packages/azathoth-mcp ./packages/azathoth-mcp

RUN python -m build --wheel --outdir /dist \
    && python -m build --wheel --outdir /dist packages/azathoth-mcp

#
# Install Azathoth, with the otel, postgres, bedrock, worker, documents and
# remote extras (ADR 0100, ADR 0102, ADR 0103, ADR 0107, ADR 0124), and its
# MCP server (ADR 0111), into a venv that is first on PATH, so the standard
# tools' child workflows run Azathoth's own Python.
#
FROM python:3.13-slim-trixie@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1

LABEL org.opencontainers.image.title="Azathoth" \
      org.opencontainers.image.description="An empirical optimization engine for context-aware AI workflows." \
      org.opencontainers.image.source="https://github.com/EldritchInc/azathoth" \
      org.opencontainers.image.url="https://github.com/EldritchInc/azathoth" \
      org.opencontainers.image.licenses="MIT"

RUN apt-get update \
    && apt-get install --yes --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 azathoth \
    && useradd --uid 10001 --gid 10001 --home-dir /var/lib/azathoth \
        --no-create-home --shell /usr/sbin/nologin azathoth \
    && install --directory --owner=10001 --group=10001 --mode=0750 /var/lib/azathoth

ENV VIRTUAL_ENV=/opt/azathoth/venv \
    PATH=/opt/azathoth/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1 \
    LANG=C.UTF-8 \
    AZATHOTH_DATABASE=/var/lib/azathoth/azathoth.db

COPY --from=builder /dist/ /tmp/dist/

RUN python -m venv /opt/azathoth/venv \
    && set -- /tmp/dist/azathoth_ai-*.whl /tmp/dist/azathoth_mcp-*.whl \
    && /opt/azathoth/venv/bin/python -m pip install --no-cache-dir --root-user-action=ignore \
        "$1[otel,postgres,bedrock,worker,documents,remote]" "$2" \
    && rm -rf /tmp/dist

WORKDIR /var/lib/azathoth

USER 10001:10001

ENTRYPOINT ["/usr/bin/tini", "--", "azathoth"]

CMD ["--help"]
