# node:22-alpine
FROM node@sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914

WORKDIR /app
COPY .npmrc package.json package-lock.json ./
# --ignore-scripts: the package's postinstall only sets up husky for its own repo
RUN npm ci --omit=dev --ignore-scripts
COPY src ./src

# Root is needed to read the Docker socket, which is mounted read-only.
CMD ["node", "src/index.js"]
