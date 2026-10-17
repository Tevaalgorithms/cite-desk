# CiteDesk web app. Build from the repository root:
#   docker build -f infrastructure/docker/web.Dockerfile -t citedesk-web .
# NEXT_PUBLIC_API_URL is baked into the page at build time. Leave it empty when a reverse proxy
# serves the API on the same address as the web app (the default setup here).
FROM node:22-alpine AS build
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
ARG NEXT_PUBLIC_API_URL=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:22-alpine
WORKDIR /web
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build /web/.next/standalone ./
COPY --from=build /web/.next/static ./.next/static
COPY --from=build /web/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
