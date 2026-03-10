FROM node:22-alpine AS frontend-deps

WORKDIR /home/frontend/

COPY ./src/frontend/package.json ./package.json
COPY ./src/frontend/package-lock.json ./package-lock.json

RUN npm ci

COPY .dockerignore ./.dockerignore
COPY ./src/frontend/ .

### ---- Front-end builder image ----
FROM frontend-deps AS dictaphone

WORKDIR /home/frontend

FROM frontend-deps AS dictaphone-dev

WORKDIR /home/frontend

EXPOSE 8080

CMD [ "npm", "run", "dev"]

# Tilt will rebuild Dictaphone target so, we dissociate dictaphone and dictaphone-builder
# to avoid rebuilding the app at every changes.
FROM dictaphone AS dictaphone-builder

WORKDIR /home/frontend

ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

# ---- Front-end image ----
FROM nginxinc/nginx-unprivileged:alpine3.21 AS frontend-production

USER root
RUN apk update && apk upgrade libssl3 \
    libcrypto3 \
    libxml2>=2.12.7-r2 \
    libxslt>=1.1.39-r2 \
    libexpat>=2.7.2-r0 \
    libpng>=1.6.53-r0 \
    && apk del curl

USER nginx

# Un-privileged user running the application
ARG DOCKER_USER
USER ${DOCKER_USER}

COPY --from=dictaphone-builder \
    /home/frontend/dist \
    /usr/share/nginx/html

COPY ./src/frontend/default.conf /etc/nginx/conf.d
COPY ./docker/files/usr/local/bin/entrypoint /usr/local/bin/entrypoint

ENTRYPOINT [ "/usr/local/bin/entrypoint" ]

CMD ["nginx", "-g", "daemon off;"]
