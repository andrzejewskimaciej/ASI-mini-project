# dev: czysty nginx, pliki podmontowane przez docker-compose
FROM nginx:1.25-alpine AS dev

RUN rm -rf /usr/share/nginx/html/*

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]


# prod: nginx z wbudowanymi assetami i skompresowaną konfiguracją
FROM nginx:1.25-alpine AS prod

RUN rm -rf /usr/share/nginx/html/*

COPY ./index.html  /usr/share/nginx/html/index.html
COPY ./style.css   /usr/share/nginx/html/style.css
COPY ./app.js      /usr/share/nginx/html/app.js

COPY ./nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]