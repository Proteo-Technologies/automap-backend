# Automap Backend

API en Python/FastAPI para el proyecto Mapa del Entorno. Expone endpoints para filtrar unidades económicas DENUE por bounding box y para calcular rutas viales via Valhalla.

## Endpoints (DENUE / rutas)

| Método | Ruta                          | Descripción                                                               |
|--------|-------------------------------|---------------------------------------------------------------------------|
| GET    | `/api/unidades-economicas`    | UEs DENUE dentro de un bbox. Query: `minLat`, `minLon`, `maxLat`, `maxLon`, `limit` (default 800), `codigos` (opcional), `incluirExcepciones` (opcional, requiere Bearer) |
| GET    | `/api/ruta`                   | Ruta entre dos puntos via Valhalla. Query: `latOrigen`, `lonOrigen`, `latDest`, `lonDest` |
| GET    | `/api/health`                 | Estado del servidor y disponibilidad de datos                             |
| GET    | `/docs`                       | Documentación interactiva (Swagger UI)                                    |

## Autenticación y mapas (requiere PostgreSQL)

Con `DATABASE_URL` configurada: registro, login (JWT), mapas/borradores (`config` JSON), presets de buffers (color/radio), plantillas de simbología.

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| POST | `/api/auth/register` | No | Alta de usuario (`email`, `password` ≥ 8 caracteres) |
| POST | `/api/auth/login` | No | Devuelve `{ "access_token", "token_type": "Bearer" }` |
| GET | `/api/auth/me` | Bearer | Perfil del usuario |
| GET/POST | `/api/maps` | Bearer | Listar / crear proyectos de mapa |
| GET/PATCH/DELETE | `/api/maps/{id}` | Bearer | Ver / actualizar / borrar |
| GET | `/api/map-profiles/global-actions` | Bearer | Acciones globales disponibles para cualquier mapa (`accion_poligono_predio`, `accion_puntos_reunion`) |
| GET | `/api/map-profiles/options` | Bearer | Opciones de configuración para crear tipo de mapa (`modo_ruta`, `modo_simbologia`) |
| GET/POST | `/api/buffer-presets` | Bearer | Presets de buffers |
| PATCH/DELETE | `/api/buffer-presets/{id}` | Bearer | Editar / borrar preset |
| GET/POST | `/api/symbology-profiles` | Bearer | Plantillas de simbología (`rules` JSON) |
| GET/PATCH/DELETE | `/api/symbology-profiles/{id}` | Bearer | Ver / editar / borrar |
| GET/POST | `/api/unidades-economicas/excepciones` | Bearer | Listar / crear UEs excepción (se muestran fuera del buffer) |
| DELETE | `/api/unidades-economicas/excepciones/{id}` | Bearer | Eliminar UE excepción |

En Swagger: **Authorize** → pegar el token (sin prefijo `Bearer ` si la UI ya lo añade; si no, `Bearer <token>`).

Migraciones: **Alembic** (`alembic/versions/`). Al arrancar con Docker se ejecuta `alembic upgrade head` automáticamente.

### Seguridad mínima (tríada CIA)

| Pilar | Qué hace el backend |
|--------|---------------------|
| **Confidencialidad** | Contraseñas con hash (**bcrypt**); tokens **JWT** firmados con `JWT_SECRET`; en `staging`/`production` con base de datos el arranque exige secreto largo y no por defecto; **TLS** debe terminarse en el proxy (HTTPS), no en este contenedor. |
| **Integridad** | Entradas validadas con **Pydantic**; consultas vía **SQLAlchemy** (parametrizadas); cabeceras **X-Content-Type-Options**, **X-Frame-Options**, **Referrer-Policy**, **Permissions-Policy**; rutas `/api/*` con **Cache-Control: no-store**. |
| **Disponibilidad** | **Rate limiting** en `POST /api/auth/login` y `POST /api/auth/register` (por IP; con `TRUSTED_PROXY=true` se usa la IP cliente de `X-Forwarded-For`); fallo rápido si la configuración es inválida; opción `EXPOSE_API_DOCS=false` para reducir superficie en producción. |

Antes de las pantallas de login en el frontend, conviene fijar `ENV`, `JWT_SECRET` y HTTPS en el entorno real.

## Instalación

```bash
cd automap-backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Configuración

Copia `.env.example` a `.env` y edita según tu entorno:

```bash
cp .env.example .env
```

Variables:

| Variable          | Valor por defecto                                 | Descripción                              |
|-------------------|---------------------------------------------------|------------------------------------------|
| `DATA_DIR`        | `./DB`                                            | Carpeta con los CSV DENUE                |
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:3001`      | URLs del frontend (CORS)                 |
| `DATABASE_URL`    | (vacío)                                           | `postgresql+asyncpg://user:pass@host:5432/db` — si está vacío, no se cargan rutas de auth/mapas en el sentido de que devolverán 503 al usar BD |
| `JWT_SECRET`      | (ver `app/core/config.py`)                        | Secreto para firmar tokens; **cámbialo en staging/producción** |
| `ENV`             | `development`                                     | `staging` o `production` activan validación estricta de `JWT_SECRET` si hay `DATABASE_URL` |
| `TRUSTED_PROXY`   | `false`                                           | `true` si hay proxy de confiable delante (rate limit por IP real) |
| `EXPOSE_API_DOCS` | `true`                                            | `false` oculta `/docs` y OpenAPI |
| `HSTS_SECONDS`      | `0`                                               | >0 envía HSTS (solo tiene sentido con HTTPS en el cliente) |

## Datos CSV

Coloca los CSV en la carpeta `DB/`:

```
DB/
├── denue_inegi_15_1.csv
└── denue_inegi_15_2.csv
```

Los archivos son grandes; se recomienda **Git LFS** (ya configurado en `.gitattributes`).

## Uso

```bash
uvicorn app.main:app --reload --port 8000
```

Abre en el navegador: **http://localhost:8000/docs**

## Docker

Solo la API:

```bash
docker build -t automap-backend .
docker run -p 8000:8000 -v %cd%/DB:/app/DB -e DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db automap-backend
```

**API + PostgreSQL** (recomendado para auth y mapas):

```bash
docker compose up --build
```

Esto levanta Postgres, aplica migraciones y arranca la API en el puerto **8000**. Usuario/clave/BD por defecto en `docker-compose.yml`: `automap` / `automap` / `automap`. Define `JWT_SECRET` en el entorno o en un archivo `.env` junto al compose.

Nombres fijos en Docker Desktop: proyecto **`automap`**, contenedores **`automap-postgres`** (base de datos) y **`automap-api`** (FastAPI). Logs: `docker compose logs -f api` o `docker logs automap-api`.

### Acceso a PostgreSQL (no es una URL en el navegador)

**`http://localhost:5432` no abre una página web.** PostgreSQL usa su propio protocolo en el puerto **5432**, no HTTP. El navegador no puede “entrar” a la base de datos como si fuera un sitio.

Datos de conexión con el `docker-compose` por defecto:

| Campo | Valor |
|--------|--------|
| Host | `localhost` (desde tu PC; dentro de Docker la API usa el hostname `db`) |
| Puerto | `5432` |
| Usuario | `automap` |
| Contraseña | `automap` |
| Base de datos | `automap` |

**Cadena típica para clientes** (DBeaver, TablePlus, DataGrip, etc.):

```text
postgresql://automap:automap@localhost:5432/automap
```

**Línea de comandos** sin instalar Postgres en Windows (entra al contenedor):

```bash
docker exec -it automap-postgres psql -U automap -d automap
```

Si tienes `psql` instalado en tu PC y el puerto **5432** está publicado:

```bash
psql -h localhost -p 5432 -U automap -d automap
```

(Te pedirá la contraseña: `automap`.)

#### Tutorial rápido: `psql` en terminal

Dentro de `psql`, los comandos que empiezan por **`\`** son “meta-comandos” del cliente (no son SQL). Terminan con **Enter**. El SQL normal termina con **`;`**.

| Comando | Qué hace |
|---------|-----------|
| `\?` | Ayuda de comandos `\` |
| `\h` | Ayuda de SQL (ej. `\h SELECT`) |
| `\q` | Salir de `psql` |
| `\conninfo` | Muestra conexión actual (usuario, BD, host) |
| `\l` | Lista **bases de datos** del servidor |
| `\c automap` | Cambia a la base de datos `automap` |
| `\dn` | Lista **esquemas** (normalmente `public`, etc.) |
| `\dt` | Lista **tablas** del esquema actual (`public` por defecto) |
| `\dt public.*` | Igual, explícito en esquema `public` |
| `\dt *.*` | Tablas de todos los esquemas a los que tienes acceso |
| `\d nombre_tabla` | **Estructura** de una tabla (columnas, tipos, índices, FK) |
| `\d+ nombre_tabla` | Lo mismo con más detalle (descripción, estadísticas) |
| `\di` | Índices del esquema actual |
| `\df` | Funciones definidas en el esquema actual |

**Revisar esquema y tablas con SQL** (estándar, útil en scripts):

```sql
-- Esquemas
SELECT schema_name
FROM information_schema.schemata
ORDER BY schema_name;

-- Tablas del esquema public
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- Columnas de una tabla (ej. users)
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'users'
ORDER BY ordinal_position;
```

**Consultas de ejemplo** (proyecto Automap):

```sql
-- Cuántos usuarios hay
SELECT count(*) AS usuarios FROM users;

-- Últimos mapas guardados (título y fecha)
SELECT title, is_draft, created_at
FROM map_projects
ORDER BY updated_at DESC
LIMIT 10;

-- Ver una fila de ejemplo (sin datos sensibles largos)
SELECT id, email, created_at FROM users LIMIT 5;
```

**Herramientas gráficas:** crea una conexión nueva con tipo PostgreSQL, host `localhost`, puerto `5432`, usuario y contraseña `automap`, base de datos `automap`. El contenedor **`automap-postgres`** debe estar en ejecución (`docker compose up -d`).

## Despliegue en Railway / Render

1. Conecta el repositorio.
2. Configura las variables de entorno `DATA_DIR` y `ALLOWED_ORIGINS`.
3. Para los CSV grandes, móntalos como volumen o usa una variable `DATA_DIR` apuntando a un bucket S3/R2 (pandas soporta `pd.read_csv("s3://...")`).
4. El `Dockerfile` se detecta automáticamente.
