FROM node:25-alpine AS extension-build

WORKDIR /extension
COPY extension/package.json extension/package-lock.json ./
RUN npm ci
COPY extension/ ./
RUN npm run zip && cp .output/*-chrome.zip /tmp/vzyalzakaz-extension-chromium.zip

FROM node:25-alpine AS build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
COPY --from=extension-build /tmp/vzyalzakaz-extension-chromium.zip ./public/downloads/vzyalzakaz-extension-chromium.zip

ARG NEXT_PUBLIC_ALLOW_DEV_AUTH=false
ARG NEXT_PUBLIC_EXTENSION_ID=
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_ALLOW_DEV_AUTH=$NEXT_PUBLIC_ALLOW_DEV_AUTH \
    NEXT_PUBLIC_EXTENSION_ID=$NEXT_PUBLIC_EXTENSION_ID
RUN npm run build

FROM node:25-alpine AS runtime

WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
