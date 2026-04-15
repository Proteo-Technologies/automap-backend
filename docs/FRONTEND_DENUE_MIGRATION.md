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
- `GET /api/map-profiles/global-actions` (nuevo, autenticado)
  - Devuelve acciones globales de mapa que aplican a cualquier perfil.
- `GET /api/map-profiles/options` (nuevo, autenticado)
  - Devuelve opciones para crear tipo de mapa: `modo_ruta` (incluye ruta o normal) y `modo_simbologia` (normal o numero).
- `POST /api/map-profiles` y `PATCH /api/map-profiles/{id}` (actualizado)
  - Ya persisten `modo_ruta` / `modo_simbologia` (ademas de nombre y capas) via `map_vista`.

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

## Excepciones UE fuera de buffer (nuevo)

- Backend ahora permite guardar una lista de UEs excepción por usuario autenticado.
- Endpoints:
  - `GET /api/unidades-economicas/excepciones`
  - `POST /api/unidades-economicas/excepciones`
  - `DELETE /api/unidades-economicas/excepciones/{id}`
- Para que el endpoint principal incluya esas UEs aunque estén fuera del bbox/buffer:
  - `GET /api/unidades-economicas?...&incluirExcepciones=true`
  - Requiere `Authorization: Bearer <token>`.
- Las UEs excepción se mezclan con el resultado normal del bbox y no se duplican.

## Rutas operativas y acciones globales

- Los perfiles de mapa por defecto (`map_vista`) ahora representan **rutas operativas**:
  - `ruta_ue_a_coordenada` (hasta 3 alternativas)
  - `ruta_coordenada_a_ue`
  - `ruta_reunion_a_ue`
  - `ruta_coordenada_ue_ida_vuelta` (ida y vuelta)
- Las siguientes piezas ya no se tratan como mapas específicos, sino como **acciones globales** disponibles en cualquier mapa:
  - `accion_poligono_predio`
  - `accion_puntos_reunion`
- Tambien quedan como acciones globales:
  - `accion_riesgos_simbologia`
  - `accion_riesgos_numero`
- Estas acciones se pueden consultar en runtime desde `GET /api/map-profiles/global-actions`.
- `accion_riesgos_simbologia` y `accion_riesgos_numero` dejan de existir como perfil por defecto.

### Llamada de frontend para rutas operativas

- Endpoint: `GET /api/rutas-operativas`
- Query base:
  - `tipo`
  - `ueLat`, `ueLon`
  - `coordLat`, `coordLon` (cuando aplique)
  - `reunionLat`, `reunionLon` (solo `reunion_a_ue`)
- Tipos recomendados (alineados con `map_vista` guardado):
  - `ruta_ue_a_coordenada` (hasta 3 alternativas)
  - `ruta_coordenada_a_ue` (1 ruta)
  - `ruta_reunion_a_ue` (1 ruta)
  - `ruta_coordenada_ue_ida_vuelta` (2 rutas: ida y vuelta)
- Compatibilidad: backend tambien acepta tipos legacy sin prefijo `ruta_`:
  - `ue_a_coordenada`, `coordenada_a_ue`, `reunion_a_ue`, `coordenada_ue_ida_vuelta`.
- Recomendacion frontend: enviar siempre los IDs con prefijo `ruta_` (los mismos que persiste `map_vista`).

### Respuesta esperada y render en frontend

- Respuesta:
  - `tipo`: tipo normalizado de ruta
  - `total`: numero de rutas devueltas
  - `rutas`: arreglo con `{ id, sentido, coordinates }`
- Para `ruta_ue_a_coordenada`:
  - Esperado: `total` hasta `3`.
  - Nota: si el motor de rutas no encuentra alternativas realmente distintas, puede devolver `1` o `2`.
- Para `ruta_coordenada_ue_ida_vuelta`:
  - Esperado: `total = 2` con `id: "ida"` y `id: "vuelta"`.
- En frontend, no asumir una sola ruta:
  - Iterar `rutas[]` y pintar todas.
  - Diferenciar por `id` o `sentido` para color/estilo.

### Ajustes recientes para evitar "solo llega 1 ruta"

- Backend reforzo la extraccion de rutas alternativas de Valhalla (principal + alternas).
- Para `ruta_ue_a_coordenada`, el backend solicita hasta 3 rutas y devuelve las disponibles en `rutas[]`.
- Importante: aunque se pidan 3, el proveedor puede devolver menos si no encuentra alternativas suficientemente distintas.
- Frontend debe renderizar **todas** las entradas de `rutas[]` y no asumir un maximo fijo.

### Validacion de punto de reunion (frontend)

- En `ruta_reunion_a_ue`, backend exige `reunionLat` y `reunionLon`.
- Si el punto de reunion coincide con la UE, backend responde `422` (coordenadas invalidas para este caso).
- Antes de invocar la ruta:
  - confirmar que el usuario realmente coloco/movio el punto de reunion,
  - leer la coordenada actual del marcador de reunion (no una referencia antigua),
  - enviar esas coordenadas en la query.

### Checklist de debug rapido (Network)

- Verificar URL final de la request:
  - `tipo` correcto (`ruta_ue_a_coordenada`, `ruta_reunion_a_ue`, etc.).
  - `coordLat/coordLon` o `reunionLat/reunionLon` presentes segun el caso.
- Verificar respuesta JSON:
  - `total` coincide con `rutas.length`.
  - Para ida/vuelta existen `id: "ida"` y `id: "vuelta"`.
  - Para alternativas existen `id: "alternativa_1"...`.
- Si llega `422`, mostrar mensaje de validacion al usuario y no hacer fallback silencioso a otra ruta.

### Persistencia al crear/editar tipo de mapa

- Al guardar un tipo de mapa, frontend puede enviar:
  - `modo_ruta`: `normal` | `ruta_ue_a_coordenada` | `ruta_coordenada_a_ue` | `ruta_reunion_a_ue` | `ruta_coordenada_ue_ida_vuelta`
  - `modo_simbologia`: `normal` | `simbologia` | `numero`
- Backend resuelve y guarda `map_vista` con esta prioridad:
  1. Si llega `map_vista`, usa ese valor.
  2. Si `modo_ruta` != `normal`, usa el modo de ruta.
  3. Si `modo_ruta` es `normal` y `modo_simbologia` != `normal`, usa:
     - `simbologia` -> `accion_riesgos_simbologia`
     - `numero` -> `accion_riesgos_numero`
  4. Si ambos son `normal`, usa `denue_general`.
- En respuestas de perfiles (`GET /api/map-profiles` y `GET /api/map-profiles/{id}`) ahora regresan:
  - `map_vista`
  - `modo_ruta`
  - `modo_simbologia`

