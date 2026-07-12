FROM node:20-slim AS dev
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 5173
# entrypoint seeds /workspace/client from this image's baked-in /app on first run
# (only if empty - never clobbers student edits), then cd's there and execs the CMD
ENTRYPOINT ["/entrypoint.sh"]
CMD ["npm", "run", "dev", "--", "--host"]

FROM node:20-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
