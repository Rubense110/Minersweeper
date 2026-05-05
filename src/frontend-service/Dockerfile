FROM node:20-alpine

WORKDIR /app/src/frontend-service

COPY src/frontend-service/package.json ./package.json
RUN npm install

COPY src/frontend-service .

EXPOSE 5173

CMD ["npm", "run", "dev"]
