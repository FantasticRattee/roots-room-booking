# Static web server for the diagrams page (docs/). Used by Railway so the page can be opened
# on a phone; it is not part of the Odoo module. Build context = the repository root.
FROM nginx:1.27-alpine
# Railway gives the port in $PORT; the nginx image fills ${PORT} into the template at start.
COPY deploy/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY docs/ /usr/share/nginx/html/
