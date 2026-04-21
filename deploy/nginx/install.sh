#!/usr/bin/env bash
# Instala/actualiza la config del nginx del host para api.proteoatlas.com.
# Ejecutar desde la raíz del repo en el VPS:
#   sudo bash deploy/nginx/install.sh
set -euo pipefail

CONF_NAME="api.proteoatlas.com"
SRC="$(dirname "$(readlink -f "$0")")/${CONF_NAME}.conf"
DEST_AVAILABLE="/etc/nginx/sites-available/${CONF_NAME}"
DEST_ENABLED="/etc/nginx/sites-enabled/${CONF_NAME}"

if [[ $EUID -ne 0 ]]; then
  echo "Debe ejecutarse con sudo/root." >&2
  exit 1
fi

if [[ ! -f "$SRC" ]]; then
  echo "No se encuentra $SRC" >&2
  exit 1
fi

cp "$SRC" "$DEST_AVAILABLE"
ln -sf "$DEST_AVAILABLE" "$DEST_ENABLED"
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl reload nginx

echo "OK: ${CONF_NAME} instalado y nginx recargado."
