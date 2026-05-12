# Build context for this Dockerfile is the monorepo root, not apps/web.
# That lets pnpm resolve workspace dependencies (@libra/shared-types,
# @libra/prompts) at install time.

FROM node:20-alpine

RUN corepack enable && corepack prepare pnpm@9.12.0 --activate

WORKDIR /repo

# Copy workspace manifests first so Docker can cache the install layer.
COPY package.json pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/shared-types/package.json packages/shared-types/package.json
COPY packages/prompts/package.json packages/prompts/package.json

RUN pnpm install --no-frozen-lockfile

# Copy the rest of the repo. In dev this is overlaid by a bind mount,
# but having the files in the image keeps the container usable on its
# own and makes initial startup deterministic.
COPY . .

WORKDIR /repo/apps/web

EXPOSE 3000

# Re-run pnpm install on every container start. With pnpm's hardlinks
# this is a near-no-op when nothing changed, but it keeps node_modules
# in sync with package.json across container restarts even when the
# anonymous node_modules volumes survive a `docker compose down`.
CMD ["sh", "-c", "cd /repo && pnpm install --no-frozen-lockfile && cd /repo/apps/web && pnpm dev"]
