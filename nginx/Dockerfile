# nginx/Dockerfile

# Start from the official Nginx image
FROM nginx:latest

# Remove the default Nginx configuration file
RUN rm /etc/nginx/conf.d/default.conf

# Copy your custom configuration, OVERWRITING the default main configuration file
COPY nginx.conf /etc/nginx/nginx.conf
