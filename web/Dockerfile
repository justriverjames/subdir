FROM node:18-alpine

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --only=production

# Copy application
COPY . .

# Expose port
EXPOSE 3000

# Run server
CMD ["node", "server.js"]
