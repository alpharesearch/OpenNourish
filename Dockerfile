# Stage 1: Build Stage
FROM python:3.12 AS build

WORKDIR /app

# Create a virtual environment
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final Stage
# Must stay on the same Python minor as the build stage: /opt/venv is copied between them and is
# not portable across interpreter versions.
FROM python:3.12-slim

# Provenance. Nothing else in this image records which checkout it came from, and the tags carried
# to TrueNAS are not identity (`deploy_truenas.sh` applies a constant V1.0.0 plus :latest), so the
# git SHA and build date are stamped at build time into three places: these labels, /app/BUILD_INFO
# below, and the banner entrypoint.sh prints. `docker compose build` supplies them through the args
# in docker-compose.yml; a bare build leaves them "unknown". No release version is claimed here —
# `.version` is deliberately absent rather than mirroring the V1.0.0 tag, which is a constant.
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="OpenNourish" \
      org.opencontainers.image.description="Self-hosted multi-user food and nutrition tracker built on USDA FoodData Central" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/alpharesearch/OpenNourish" \
      org.opencontainers.image.url="https://github.com/alpharesearch/OpenNourish" \
      org.opencontainers.image.licenses="MIT"

# Install font dependencies and Typst
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    fontconfig \
    fonts-liberation \
    xz-utils \
    dos2unix \
    openssl \
    --no-install-recommends && \
    wget https://github.com/typst/typst/releases/download/v0.15.1/typst-x86_64-unknown-linux-musl.tar.xz && \
    tar -xf typst-x86_64-unknown-linux-musl.tar.xz && \
    mkdir -p /usr/local/bin/typst && \
    mv typst-x86_64-unknown-linux-musl/* /usr/local/bin/typst/ && \
    rm typst-x86_64-unknown-linux-musl.tar.xz && \
    rmdir typst-x86_64-unknown-linux-musl && \
    rm -rf /var/lib/apt/lists/*

# Add Typst to the PATH. Declared here, before the vendoring step below, so that step can run
# `typst`; it stays in effect for the runtime either way.
ENV PATH="/usr/local/bin/typst:$PATH"

# Vendor the @preview Typst packages that the nutrition-label templates import.
#
# typst downloads a package from packages.typst.org the first time a document imports it, and caches
# the unpacked files under $TYPST_PACKAGE_CACHE_PATH. Without this step, every fresh container's
# first label render needed outbound internet — and a container without egress answered 500
# (`upgrade-research/PLAN.md` M5). Both packages are MIT: `nutrition-label-nam` is this project's own
# template published to the registry, `codetastic` supplies the barcode. 164 KB unpacked, 16 files.
#
# The list is derived from the templates in `opennourish/typst_utils.py` rather than repeated here, so
# the version pins live in exactly one place — same reasoning as ci.yml grepping the typst URL above.
# Only that file is copied into this layer, which keeps the layer stable across application edits, and
# it is why the non-empty guard is not decoration: if the templates ever move out of `typst_utils.py`,
# grep matches nothing and this build fails loudly instead of silently vendoring nothing. The `--deps`
# check proves each listed spec was really resolved from the cache, and the second compile repeats the
# build with every proxy black-holed, which is what makes "the image is self-sufficient" a verified
# property and not an intention.
ENV TYPST_PACKAGE_CACHE_PATH=/opt/typst/packages
COPY opennourish/typst_utils.py /tmp/typst-vendor/typst_utils.py
RUN set -eux; \
    mkdir -p "$TYPST_PACKAGE_CACHE_PATH"; \
    grep -hoE '@preview/[A-Za-z0-9._-]+:[0-9]+\.[0-9]+\.[0-9]+' /tmp/typst-vendor/typst_utils.py \
      | sort -u > /tmp/typst-vendor/specs.txt; \
    test -s /tmp/typst-vendor/specs.txt; \
    awk '{ print "#import \"" $0 "\" as vendored" NR }' /tmp/typst-vendor/specs.txt \
      > /tmp/typst-vendor/probe.typ; \
    typst compile --deps /tmp/typst-vendor/deps.json /tmp/typst-vendor/probe.typ \
      /tmp/typst-vendor/probe.pdf; \
    while read -r spec; do \
      grep -q "preview/$(printf '%s' "${spec#@preview/}" | tr ':' '/')/" /tmp/typst-vendor/deps.json; \
    done < /tmp/typst-vendor/specs.txt; \
    rm -f /tmp/typst-vendor/probe.pdf; \
    HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9 \
      typst compile /tmp/typst-vendor/probe.typ /tmp/typst-vendor/probe.pdf; \
    chmod -R a+rX "$TYPST_PACKAGE_CACHE_PATH"; \
    rm -rf /tmp/typst-vendor

WORKDIR /app

# Copy virtual environment from build stage
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy the entire application context, respecting .dockerignore
COPY . .

# Set the FLASK_APP environment variable
ENV FLASK_APP=app.py

# Bake the same provenance into the filesystem, because `docker inspect` is unavailable from inside
# a TrueNAS custom app or a shell exec, while `cat /app/BUILD_INFO` always works. The requirements
# hash pins which lock is actually inside the image, and the live versions are re-checked at boot by
# entrypoint.sh.
RUN { \
      echo "revision=${VCS_REF}"; \
      echo "built=${BUILD_DATE}"; \
      echo "source=https://github.com/alpharesearch/OpenNourish"; \
      echo "python=$(python -V 2>&1)"; \
      echo "typst=$(typst --version | head -n1)"; \
      echo "typst_packages=$(find "$TYPST_PACKAGE_CACHE_PATH/preview" -mindepth 2 -maxdepth 2 -type d | sed -E "s|.*/preview/|@preview/|; s|/([^/]+)$|:\1|" | LC_ALL=C sort | paste -sd" " -)"; \
      echo "requirements_sha256=$(sha256sum requirements.txt | cut -d' ' -f1)"; \
      echo "packages=$(pip freeze | wc -l)"; \
    } > /app/BUILD_INFO

# Expose the port Flask will run on
EXPOSE 8081

# Copy and set up the entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN dos2unix /app/entrypoint.sh /app/safe_upgrade.sh && chmod +x /app/entrypoint.sh /app/safe_upgrade.sh
ENTRYPOINT ["/app/entrypoint.sh"]

# Command to run the application
CMD ["python", "-u", "serve.py"]
