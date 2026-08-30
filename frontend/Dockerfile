FROM node:25-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

ARG NEXT_PUBLIC_ALLOW_DEV_AUTH=false
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_ALLOW_DEV_AUTH=$NEXT_PUBLIC_ALLOW_DEV_AUTH
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
