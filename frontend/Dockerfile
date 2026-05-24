FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# Build with the in-Docker backend URL baked into the rewrites
ARG PYTHON_API_URL=http://backend:8080
ENV PYTHON_API_URL=$PYTHON_API_URL

RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
