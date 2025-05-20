#!/bin/sh
echo "Starting HTTP server..."
echo "Files available at http://0.0.0.0:80"
exec nginx -g "daemon off;"