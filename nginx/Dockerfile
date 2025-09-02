# nginx/Dockerfile

# Start from the official Nginx image
FROM nginx:1.29

# Install dependencies needed by our entrypoint script
RUN apt-get update && apt-get install -y openssl && rm -rf /var/lib/apt/lists/*

# Copy your custom Nginx configuration, replacing the main one
COPY nginx.conf /etc/nginx/nginx.conf

# Copy the intelligent entrypoint script
COPY entrypoint.sh /docker-entrypoint.sh

# Make the script executable
RUN chmod +x /docker-entrypoint.sh

# Set the entrypoint
ENTRYPOINT ["/docker-entrypoint.sh"]

# The default Nginx command will be passed to the entrypoint script by `exec "$@"`
CMD ["nginx", "-g", "daemon off;"]