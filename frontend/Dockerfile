FROM node:20-slim AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install
COPY . .
ARG VITE_BASE_URL
ENV VITE_BASE_URL=$VITE_BASE_URL
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
ENV API_GATEWAY_HOST=api-gateway
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
