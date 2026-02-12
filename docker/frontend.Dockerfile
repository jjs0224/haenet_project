# docker/frontend.Dockerfile
FROM node:20-alpine AS build
WORKDIR /app

ARG REACT_APP_API_BASE_URL=/api
ENV REACT_APP_API_BASE_URL=${REACT_APP_API_BASE_URL}

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build && \
    if [ -d dist ]; then cp -r dist /out; \
    elif [ -d build ]; then cp -r build /out; \
    else echo "No build output (dist/build) found"; ls -la; exit 1; fi

FROM nginx:alpine AS runtime
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /out /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
