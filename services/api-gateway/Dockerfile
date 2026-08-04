FROM node:20-slim AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install
COPY . .
RUN npx prisma generate
RUN npm run build

FROM node:20-slim 
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install --omit=dev
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/generated ./generated
EXPOSE 3000
CMD ["node","dist/main.js"]