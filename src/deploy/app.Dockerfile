# The demo app's image: the Svelte page, built with Node, served by FastAPI on Python 3.14.
# It is built on the GPU host from this repository, so there is no registry to push to:
#   docker compose --env-file /etc/sys1.env -f src/deploy/compose.yaml build app
# The build context is the repository root. app.Dockerfile.dockerignore, beside this file, lets in
# only what the build copies [https://docs.docker.com/build/concepts/context/#filename-and-location].

# Stage 1, the page: npm ci installs exactly what package-lock.json records, and vite build
# writes the finished page to dist/.
FROM node:24-slim AS page
WORKDIR /src/web
COPY src/web/package.json src/web/package-lock.json ./
RUN npm ci
COPY src/web/ ./
RUN npm run build

# Stage 2, the app, on the uv release that wrote uv.lock (0.11.7) and CPython 3.14
# [https://docs.astral.sh/uv/guides/integration/docker/, as-of 2026-10-02].
FROM ghcr.io/astral-sh/uv:0.11.7-python3.14-trixie-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# The dependencies first, in their own layer, so a change to the code does not reinstall them.
# --locked stops the build if uv.lock is out of date; --no-dev leaves the test tools out.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev
COPY src/app ./src/app
# The app serves the page from src/web/dist, beside its own package.
COPY --from=page /src/web/dist ./src/web/dist

# Shell form on purpose, which SHELL makes explicit, so that $APP_PORT from compose expands
# when the container starts; exec puts uv in the shell's place, so docker stop's signal reaches it.
SHELL ["/bin/sh", "-c"]
CMD exec uv run --frozen --no-dev uvicorn app.main:create_app --factory --app-dir src --host 0.0.0.0 --port "$APP_PORT"
