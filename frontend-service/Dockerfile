FROM node:20-alpine

WORKDIR /app/frontend-service

COPY frontend-service/package.json ./package.json
RUN npm install

COPY frontend-service .

EXPOSE 5173

CMD ["npm", "run", "dev"]
