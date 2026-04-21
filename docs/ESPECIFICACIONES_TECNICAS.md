# Especificaciones técnicas — Automap Backend

Documento orientado a equipos de desarrollo, operaciones y auditoría: stack, dependencias, coste/licencia a alto nivel y requisitos para un despliegue en producción.

---

## 1. Resumen

**Automap Backend** es una API HTTP (REST) que sirve datos de unidades económicas DENUE a partir de archivos CSV locales, calcula rutas vía un servicio Valhalla externo y, cuando hay base de datos configurada, ofrece autenticación JWT, perfiles de mapa, presets de buffer y plantillas de simbología.

---

## 2. Lenguajes y runtime

| Elemento | Detalle |
|----------|---------|
| **Lenguaje** | Python **3.12** (imagen base `python:3.12-slim` en Docker) |
| **Estilo** | Tipado con anotaciones (`from __future__ import annotations` donde aplica), módulos `app/` |
| **Servidor ASGI** | **Uvicorn** (`uvicorn app.main:app`) |
| **Paradigma API** | **FastAPI**: rutas asíncronas, esquemas con **Pydantic v2**, validación en request/response |
| **Configuración** | Variables de entorno y archivo `.env` vía **pydantic-settings** y **python-dotenv** |

---

## 3. Frameworks y métodos principales

| Área | Tecnología / método |
|------|---------------------|
| **HTTP** | FastAPI routers (`GET`, `POST`, `PATCH`, `DELETE`), middleware CORS y cabeceras de seguridad personalizadas |
| **Persistencia** | **SQLAlchemy 2.x** en modo **async** (`asyncio`) con driver **asyncpg** para PostgreSQL |
| **Migraciones** | **Alembic**; en contenedor: `alembic upgrade head` antes de arrancar Uvicorn si existe `DATABASE_URL` |
| **Autenticación** | **JWT** (`python-jose` + algoritmo **HS256**); contraseñas con **passlib** y **bcrypt** (versión acotada por compatibilidad con passlib) |
| **Abuso / disponibilidad** | **slowapi** — rate limiting en login y registro por IP (opción `TRUSTED_PROXY` para IP real detrás de proxy) |
| **Datos tabulares** | **pandas** — lectura de CSV DENUE con detección de encoding en `app/services/csv_reader.py` |
| **Cliente HTTP saliente** | **httpx** (async) — llamadas a Valhalla para rutas y localización |
| **Documentación API** | OpenAPI / **Swagger UI** y ReDoc (configurables con `EXPOSE_API_DOCS`) |

---

## 4. Librerías de terceros (requirements.txt)

Todas las dependencias listadas en el proyecto son **paquetes de código abierto** instalables con **pip** desde PyPI (uso gratuito en sentido de licencia del software; el hosting y los datos son costes aparte).

| Paquete | Rol |
|---------|-----|
| `fastapi` | Framework web y OpenAPI |
| `uvicorn[standard]` | Servidor ASGI |
| `pandas` | Procesamiento de CSV DENUE |
| `httpx` | Cliente HTTP hacia Valhalla |
| `python-dotenv` | Carga de `.env` |
| `sqlalchemy[asyncio]` | ORM y capa de acceso async |
| `asyncpg` | Driver PostgreSQL async |
| `alembic` | Migraciones de esquema |
| `passlib[bcrypt]` | Hash de contraseñas |
| `bcrypt` | Backend criptográfico (rango de versión fijado por compatibilidad) |
| `python-jose[cryptography]` | JWT |
| `pydantic[email]` | Validación y tipos (incl. email) |
| `pydantic-settings` | Settings desde entorno |
| `psycopg2-binary` | Driver PostgreSQL síncrono (p. ej. uso desde Alembic u operaciones que lo requieran) |
| `slowapi` | Rate limiting |

**Dependencias del sistema (Dockerfile):** en la imagen se instala `build-essential` (compilación) para satisfacer dependencias nativas de la cadena de instalación (p. ej. extensiones usadas por paquetes Python).

---

## 5. Servicios externos y modelo de coste

| Recurso | Uso en el proyecto | ¿Gratis? |
|---------|-------------------|----------|
| **PostgreSQL** | Base de datos propia (contenedor, PaaS o servidor gestionado) | Software **open source**; el **servicio gestionado** puede ser de pago (RDS, Neon, Supabase, etc.) o autoalojado sin licencia de Postgres |
| **Valhalla (OSM)** | Por defecto `https://valhalla1.openstreetmap.de/route` y `/locate` — enrutamiento y localización | Servicio **público y gratuito** ofrecido por la comunidad; **sin SLA**, sujeto a límites de uso, caídas y políticas del operador. Para producción exigente conviene **Valhalla propio** u otro proveedor de rutas (posible **coste** de infra o API comercial) |
| **Datos DENUE (CSV)** | Archivos locales en `DATA_DIR` (p. ej. `DB/`) | Los datos **INEGI DENUE** tienen **condiciones de uso** propias del INEGI; no es “software de pago”, pero hay que cumplir licencia/atribución según normativa aplicable |
| **PyPI / Docker Hub** | Descarga de imágenes y paquetes | Gratuitos para uso estándar; cuentas o mirrors privados pueden implicar coste |

**Conclusión:** El código y las librerías principales son **gratuitas en licencia (open source)**. Los costes típicos en producción vienen de **infraestructura** (servidor, disco, base de datos gestionada), **opcionalmente** de un **motor de rutas** propio o de pago, y del **cumplimiento** de términos de datos oficiales.

---

## 6. Infraestructura recomendada para producción

### 6.1 Componentes obligatorios u opcionales

| Componente | Obligatorio | Notas |
|------------|-------------|--------|
| **Proceso Uvicorn** (API) | Sí | Escuchar en el puerto configurado (p. ej. 8000); detrás de un **reverse proxy** con TLS |
| **PostgreSQL** | Sí si se usan registro, login, mapas, buffers, simbología, excepciones UE | Versión compatible con SQL generado por el proyecto (p. ej. **16** como en `docker-compose.yml`) |
| **Volumen / disco para CSV** | Sí para endpoints DENUE que lean archivos | Los CSV son **grandes**; el README menciona **Git LFS** y en `render.yaml` hay ejemplo de **disco persistente** (p. ej. 5 GB); dimensionar según conjuntos DENUE |
| **TLS (HTTPS)** | Muy recomendable | Terminación en **Nginx**, **Caddy**, **Traefik**, balanceador de cloud, etc. La app puede enviar **HSTS** si `HSTS_SECONDS > 0` |
| **Proxy de confianza** | Si hay balanceador/CDN | `TRUSTED_PROXY=true` solo si `X-Forwarded-For` es fiable |

### 6.2 Variables de entorno (producción)

Definir al menos:

- `DATABASE_URL` — `postgresql+asyncpg://usuario:contraseña@host:5432/base`
- `JWT_SECRET` — cadena aleatoria larga (en `staging`/`production` con BD activa el arranque exige secreto fuerte y no por defecto)
- `ENV=production` (o `staging` según política)
- `ALLOWED_ORIGINS` — orígenes exactos del frontend (CORS)
- `DATA_DIR` — ruta absoluta donde están los CSV (p. ej. `/app/DB` en contenedor)
- Opcional: `TRUSTED_PROXY`, `EXPOSE_API_DOCS=false`, `HSTS_SECONDS`

Ver `.env.example` y tabla del `README.md` para el detalle.

### 6.3 Recursos de cómputo (orientación)

No hay benchmarks fijados en el repositorio; orientación práctica:

- **RAM:** pandas carga fragmentos de CSV en memoria según consultas; conviene **varios GB** (p. ej. **2–8 GB** o más) si hay muchas peticiones concurrentes o CSV muy grandes.
- **CPU:** 1–2 vCPU suele bastar para tráfico moderado; aumentar si hay mucho filtrado DENUE concurrente.
- **Disco:** además del volumen de datos DENUE, espacio para logs y contenedor; PostgreSQL necesita su propio almacenamiento dimensionado.

### 6.4 Red y seguridad

- Abrir al público solo el **puerto HTTPS** del proxy; la API puede quedar en red interna.
- Restringir PostgreSQL a red privada o allowlist de IPs.
- Rotar `JWT_SECRET` implica invalidar sesiones existentes; planificar cambios.

### 6.5 Despliegue con Docker

- **Imagen:** `Dockerfile` multi-etapa mínima: Python 3.12-slim, pip install, `CMD` con migración condicional y Uvicorn.
- **Compose de referencia:** `docker-compose.yml` — servicios `postgres:16-alpine` y API con volumen `./DB:/app/DB`.

### 6.6 Plataformas mencionadas en el proyecto

- **Render:** `render.yaml` — servicio web Docker, variables sincronizadas desde dashboard, disco montado en `/app/DB` para datos DENUE.
- **Railway / otros PaaS:** el README indica flujo similar (repo + env + Dockerfile).

---

## 7. Herramientas de desarrollo y CI (referencia)

- Entorno virtual Python + `pip install -r requirements.txt`
- **Git** / opcionalmente **Git LFS** para CSV grandes (`.gitattributes`)
- Clientes SQL contra PostgreSQL (DBeaver, `psql`, etc.) para operación

---

## 8. Versionado y mantenimiento

- Versionado de API declarado en `app/main.py` (campo `version` de FastAPI).
- Actualizar dependencias con cuidado: hay **pin explícito** de `bcrypt` por compatibilidad con `passlib`; cambiar sin probar puede romper registro/login.

---

*Documento generado a partir del código y configuración del repositorio Automap Backend. Para cambios de comportamiento concretos, prevalece el código fuente y el README principal.*
