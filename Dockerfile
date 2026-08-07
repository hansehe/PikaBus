FROM python:3.13-slim AS dev

# uv ships as a static binary, so copying it in beats installing it.
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Dependencies first, without the project itself, so this layer is cached across source edits.
# --locked fails the build if uv.lock is stale rather than silently resolving something else.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

FROM dev AS final

COPY . .

RUN uv sync --locked

ENV RUNNING_IN_CONTAINER=true

# Exec form, and the -p pattern is quoted: in shell form the glob could be expanded by the shell
# before unittest ever sees it.
ENTRYPOINT ["uv", "run", "--no-sync", "python", "-m", "unittest", "discover", "-p", "*Test*.py"]
