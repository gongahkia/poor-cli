FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY packages/shared/package.json packages/shared/
COPY packages/mcp-server/package.json packages/mcp-server/
COPY packages/skill/package.json packages/skill/
RUN npm ci
COPY tsconfig.base.json tsconfig.json ./
COPY packages/shared packages/shared
COPY packages/mcp-server packages/mcp-server
COPY packages/skill packages/skill
RUN npm run build

FROM node:20-slim
WORKDIR /app
COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/packages/shared/package.json packages/shared/
COPY --from=build /app/packages/mcp-server/package.json packages/mcp-server/
COPY --from=build /app/packages/skill/package.json packages/skill/
RUN npm ci --omit=dev
COPY --from=build /app/packages/shared/dist packages/shared/dist
COPY --from=build /app/packages/mcp-server/dist packages/mcp-server/dist
COPY --from=build /app/packages/skill packages/skill
ENTRYPOINT ["node", "packages/mcp-server/dist/index.js"]
