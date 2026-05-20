FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY packages/shared/package.json packages/shared/
COPY packages/sdk/package.json packages/sdk/
COPY packages/mcp-server/package.json packages/mcp-server/
COPY packages/mcp-server/openapi.json packages/mcp-server/
COPY apps/web/package.json apps/web/
RUN npm ci
COPY tsconfig.base.json tsconfig.json ./
COPY packages/shared packages/shared
COPY packages/sdk packages/sdk
COPY packages/mcp-server packages/mcp-server
COPY apps/web apps/web
RUN npm run build -- --force && npm run build -w apps/web

FROM node:20-slim
LABEL io.modelcontextprotocol.server.name="io.github.gongahkia/dude-mcp"
WORKDIR /app
COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/packages/shared/package.json packages/shared/
COPY --from=build /app/packages/mcp-server/package.json packages/mcp-server/
COPY --from=build /app/packages/mcp-server/openapi.json packages/mcp-server/
COPY --from=build /app/packages/mcp-server/assets packages/mcp-server/assets
RUN npm ci --omit=dev
COPY --from=build /app/packages/shared/dist packages/shared/dist
COPY --from=build /app/packages/mcp-server/dist packages/mcp-server/dist
COPY --from=build /app/apps/web/dist apps/web/dist
ENTRYPOINT ["node", "packages/mcp-server/dist/index.js"]
