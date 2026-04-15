# Migracion Frontend: clasificacion DENUE desde backend

Este documento resume los cambios recientes para que frontend elimine logica de reclasificacion que ya no le corresponde.

## Objetivo

- Backend ahora entrega una clasificacion simplificada por UE.
- Frontend debe consumir esa clasificacion tal cual, sin volver a mapear codigos SCIAN.

## URL base y proxy

- La API FastAPI corre por defecto en `http://localhost:8000` (ver `README.md`).
- Si el frontend usa `http://localhost:3000/api/...`, Next (o similar) debe **reenviar** esa ruta al backend en el puerto **8000**. Si el proxy no esta configurado o el backend no esta levantado, veras mensajes tipo "API no disponible".
- Para comprobar el backend sin pasar por el frontend, abre en el navegador:
  - `http://localhost:8000/docs`
  - `http://localhost:8000/api/health`

## Endpoints relevantes

- `GET /api/unidades-economicas`
  - Query existente: `minLat`, `minLon`, `maxLat`, `maxLon`, `limit`
  - Query opcional: `codigos` + `modoCodigos=prefix|exact`
  - Query opcional: `archivos`
- `GET /api/unidades-economicas/categorias` (nuevo)
  - Devuelve el catalogo de categorias simplificadas disponibles para simbologia.

## Cambios en payload de UEs

Cada UE ahora incluye:

- `lat`
- `lon`
- `codigo_act`
- `nombre_act` (actividad SCIAN)
- `nom_estab` (nombre del establecimiento)
- `categoria` (clasificacion simplificada backend)

Ejemplo:

```json
{
  "lat": 19.28725929,
  "lon": -99.63714314,
  "codigo_act": "931412",
  "nombre_act": "Mantenimiento de la seguridad y el orden publico",
  "nom_estab": "COORDINACION MUNICIPALDE PROTECCION CIVIL Y BOMBEROS",
  "categoria": "bomberos"
}
```

## Categorias simplificadas actuales

- `bomberos`
- `almacen_sustancias_peligrosas`
- `recicladoras`
- `restaurantes`
- `gaseras`
- `industria`
- `escuelas`
- `hospitales`
- `hoteles`
- `iglesias`
- `museos`
- `gasolineras`
- `policia`
- `oficinas`
- `otros`

Nota: frontend debe leer el catalogo en runtime usando `GET /api/unidades-economicas/categorias`.

### Codigos SCIAN usados para nuevas categorias

- `almacen_sustancias_peligrosas`: `49319`
- `recicladoras`: `56292`, `43422`, `434311`, `434312`, `434313`
- `restaurantes`: `722`
- `gaseras`: `468413`, `468414`

## Como se calcula `categoria` (backend)

- Casi siempre por **`codigo_act` (SCIAN)** con prefijos definidos en backend.
- **No** se usa el nombre del establecimiento para “adivinar” categoria (evita falsos positivos como nombres comerciales con “Bomberos”).
- Excepcion: codigo **931412** (orden publico / seguridad); ahi el nombre ayuda a distinguir `bomberos` / `policia` / `oficinas`.

## Logica que frontend debe eliminar

- Reclasificacion de `codigo_act` en cliente.
- Reglas por texto para inferir categoria.
- Mapeos internos de iconos basados en prefijos SCIAN.
- Uso de `nombre_act` como unico nombre visible del marcador.

## Logica recomendada en frontend

- Usar `categoria` para elegir icono/color.
- Usar `nom_estab` como titulo principal del marcador/popup.
- Usar `nombre_act` como subtitulo informativo.
- Mantener `codigo_act` solo para detalle y debug.

## Compatibilidad y transicion

- Si algun registro llega sin `categoria`, usar fallback visual `otros`.
- Si algun registro llega con `nom_estab` vacio, mostrar `nombre_act`.
- No asumir lista fija de categorias: preferir el endpoint de catalogo.

## Gasolineras y conteos

- En backend, la categoria `gasolineras` usa codigos SCIAN **468411**, **468412** y **468419** (venta de combustibles al por menor). No entran **468211** (autopartes), **468311** (motos), etc., aunque el nombre comercial suene parecido.
- Si el mapa muestra un bbox muy pequeno, puede haber una gasolinera DENUE a **cientos de metros** del centro del recuadro y no aparecer: el filtro es por coordenadas dentro del bbox, no por distancia al centro.
- Con **varios CSV** en `DATA_DIR`, el cupo `limit` se reparte entre archivos (tambien cuando se usa `codigos`), para no perder UEs que esten solo en el segundo archivo.

## Diagnostico: "API no disponible" al pedir UEs

1. Confirma que el backend esta corriendo (`uvicorn app.main:app --reload --port 8000`).
2. Prueba directo contra el backend (sin puerto 3000), mismo bbox y `limit`.
3. Si usas proxy en `:3000`, revisa **timeout**: consultas con `limit` alto y varios CSV pueden tardar varios segundos; un timeout corto (p. ej. 3 s) corta la peticion y el cliente muestra error generico.
4. Baja `limit` en desarrollo (p. ej. 800–1500) si el mapa no lo necesita todo a la vez.

