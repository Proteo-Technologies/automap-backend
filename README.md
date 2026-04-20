# Automap Backend

API en Python/FastAPI para el proyecto Mapa del Entorno. Expone endpoints para filtrar unidades económicas DENUE por bounding box y para calcular rutas viales via Valhalla.

## Endpoints

| Método | Ruta                          | Descripción                                                               |
|--------|-------------------------------|---------------------------------------------------------------------------|
| GET    | `/api/unidades-economicas`    | UEs DENUE dentro de un bbox. Query: `minLat`, `minLon`, `maxLat`, `maxLon`, `limit` (default 800), `codigos` (opcional, prefijos separados por coma) |
| GET    | `/api/ruta`                   | Ruta entre dos puntos via Valhalla. Query: `latOrigen`, `lonOrigen`, `latDest`, `lonDest` |
| GET    | `/api/health`                 | Estado del servidor y disponibilidad de datos                             |
| GET    | `/docs`                       | Documentación interactiva (Swagger UI)                                    |

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

### API único (sin balanceador)

```bash
docker build -t automap-backend .
docker run -p 8000:8000 -v $(pwd)/DB:/app/DB automap-backend
```

### Nginx + balanceo de carga (compose)

Copia `.env.example` a `.env` si quieres cambiar `DATA_DIR` o `ALLOWED_ORIGINS`.

```bash
docker compose up -d --build
```

La API queda detrás de nginx en el puerto **8000** (o el que definas en `PUBLIC_PORT`). Para varias réplicas del backend:

```bash
docker compose up -d --build --scale backend=4
```

Nginx reparte las peticiones entre los contenedores `backend` usando el DNS interno de Docker (`resolver 127.0.0.11`) y cabeceras de proxy.

## Despliegue en Railway / Render

1. Conecta el repositorio.
2. Configura las variables de entorno `DATA_DIR` y `ALLOWED_ORIGINS`.
3. Para los CSV grandes, móntalos como volumen o usa una variable `DATA_DIR` apuntando a un bucket S3/R2 (pandas soporta `pd.read_csv("s3://...")`).
4. El `Dockerfile` se detecta automáticamente.
