# Frontend: rutas operativas y alternativas (última actualización)

Este documento describe el comportamiento actual del backend para **rutas viales** y qué debe asumir el frontend al pintar **varias alternativas** en el mapa.

## Objetivo del producto

- En el flujo **UE → coordenada** el backend intenta devolver **3 rutas** (`alternativa_1`, `alternativa_2`, `alternativa_3`).
- Las alternativas deben ser **geometrías distintas** cuando la red vial lo permite (no se rellena con tres copias idénticas de la primera ruta salvo casos extremos).
- El destino se **ancla primero a la calle más cercana** al punto solicitado (servicio `locate` de Valhalla) para calcular la vía. Tras elegir las tres alternativas, el backend **ajusta el último vértice** al par `coordLat`/`coordLon` solicitado cuando la calle está a ≤ ~95 m (las tres polylines comparten el **mismo punto final** del pin).
- La elección del trío prioriza **bajo solapamiento** entre pares (objetivo ≤30 % de tramos compartidos en la heurística por celdas), no solo “tres rutas cualquiera”.

## URL base y comprobación

- API por defecto: `http://localhost:8000` (ver `README.md`).
- Swagger: `http://localhost:8000/docs`.
- Salud: `GET /api/health` (misma base, p. ej. `http://localhost:8000/api/health`).

## Endpoints: uno es una sola ruta, el otro son hasta tres

| Endpoint | Uso |
|----------|-----|
| `GET /api/ruta` | **Una sola** polyline entre dos puntos. Query: `latOrigen`, `lonOrigen`, `latDest`, `lonDest`. Respuesta: `{ "coordinates": [[lat, lon], ...] }`. |
| `GET /api/rutas-operativas` | Rutas según **tipo** de operación. Para **3 alternativas**, usar `tipo=ue_a_coordenada` (o alias `ruta_ue_a_coordenada`). |

Si el mapa de “tres alternativas” llama a `/api/ruta`, solo verá **una** línea. Debe usar **`/api/rutas-operativas`**.

## Contrato: `GET /api/rutas-operativas` (UE → coordenada)

### Query requerida

- `tipo`: `ue_a_coordenada` (o alias `ruta_ue_a_coordenada`).
- `ueLat`, `ueLon`: posición de la unidad económica (origen).
- `coordLat`, `coordLon`: punto de destino (el pin / objetivo operativo).

### Respuesta (forma actual)

```json
{
  "tipo": "ue_a_coordenada",
  "total": 3,
  "rutas": [
    { "id": "alternativa_1", "sentido": "ida", "coordinates": [[lat, lon], ...] },
    { "id": "alternativa_2", "sentido": "ida", "coordinates": [[lat, lon], ...] },
    { "id": "alternativa_3", "sentido": "ida", "coordinates": [[lat, lon], ...] }
  ]
}
```

- Cada elemento de `rutas` es una polyline independiente en orden **[lat, lon]** (igual que `/api/ruta`).
- `total` coincide con `rutas.length` (3 en este tipo).

### Ejemplo de llamada (origen UE, destino punto)

Coordenadas de ejemplo usadas en pruebas:

- UE: `19.284913`, `-99.641528`
- Punto: `19.286837`, `-99.637390`

```http
GET /api/rutas-operativas?tipo=ue_a_coordenada&ueLat=19.284913&ueLon=-99.641528&coordLat=19.286837&coordLon=-99.637390
```

## Qué debe hacer el frontend al dibujar

1. **Iterar `rutas`** y crear **una capa o una fuente GeoJSON por alternativa** usando `coordinates` de cada ítem.
2. **No deduplicar** polylines solo porque comparten el **primer o último punto**; en trayectos cortos varias alternativas pueden compartir tramos iniciales y divergir después.
3. **Sí** es razonable evitar pintar dos veces la **misma** lista exacta de vértices (por ejemplo comparando un hash estable de la secuencia redondeada); el backend ya intenta no enviar tres geometrías idénticas.
4. Si `total === 3` pero el usuario “ve una sola línea”, revisar:
   - que no se esté usando `/api/ruta`;
   - que no se esté tomando solo `rutas[0]`;
   - que el estilo no superponga tres colores en el mismo orden de capas sin opacidad / sin desplazamiento visual;
   - que no haya un `Map`/`Set` keyed por destino que descarte “duplicados” de ruta.

## Comportamiento backend (resumen técnico)

- Motor: **Valhalla** (`/route` y `locate` públicos).
- Destino: correlación a **calle más cercana** antes de calcular alternativas.
- Alternativas en trayectos cortos: candidatos con **puntos vía** (`through` en una sola petición) para diversificar sin multiplicar HTTP; el grado de agresividad depende de la distancia (ver siguiente apartado).
- Se aplican filtros para **rodeos extremos**, rutas **muy “en círculo”** heurísticamente, y límites de **solapamiento** entre pares de rutas cuando el pool lo permite.
- Si la red no admite tres trazos claramente distintos, el backend **relaja** solapamiento y deduplicación “casi idénticas” de forma progresiva. La prioridad es **tres firmas de geometría distintas** en el JSON; se aceptan trayectos más largos antes que repetir la misma polyline. Solo en caso extremo (pool insuficiente) se duplica una ruta para mantener `total: 3`.

## Trayectos cortos urbanos (calidad de polyline)

En `app/services/valhalla.py`, **`_urban_short_trip_params(distancia_m)`** ajusta límites de longitud, cuántos **`approach_through`**, cuántos desvíos `through` y si se usa malla densa, según la distancia **origen → destino correlacionado**.

| Distancia (orden de magnitud) | Efecto principal |
|------------------------------|------------------|
| **≤ ~1,1 km** | Más candidatos (aprox. lateral, desvíos, malla si hace falta) y techo de longitud más alto (~**1,68×** la ruta más corta) para no descartar alternativas útiles. El **pool de relleno** incluye también rutas válidas que solo se salían del factor de longitud “corto”. |
| **~1,1–1,8 km** y **~1,8–2,5 km** | Límites intermedios; mismo criterio: el pool amplio alimenta `_fill_with_distinct_geometries` / `_greedy_add_by_dissimilarity` antes de repetir geometría. |
| **> ~2,5 km** (flujo “corto” del código) | Comportamiento amplio; podado por longitud relativa solo si siguen sobrando **firmas** distintas. |

El frontend **no** debe reimplementar esta lógica: solo consume `GET /api/rutas-operativas`. Si el mapa muestra **una sola línea** pero la leyenda tiene tres colores, inspecciona en red que las tres `coordinates` no sean la misma secuencia; si lo son, el fallo está en el pool de Valhalla o en el backend, no en el pintado por compartir color.

## Otros `tipo` en el mismo endpoint

- `coordenada_a_ue`: **una** ruta hacia la UE.
- `reunion_a_ue`: **una** ruta desde el punto de reunión.
- `coordenada_ue_ida_vuelta`: **dos** rutas (`ida`, `vuelta`).

## Errores habituales

| Código | Causa típica |
|--------|----------------|
| `422` | Faltan `coordLat`/`coordLon` para `ue_a_coordenada`, o reunión inválida en `reunion_a_ue`. |
| `404` | Valhalla no devolvió geometría usable. |
| `502` | Fallo de red / timeout hacia Valhalla. |

## Diagnóstico según tus logs (`operativas_excepcion`, CORS, 429)

### 1. `error: 'signal is aborted without reason'` y luego `fallback_una_sola_polyline`

Eso **no** es un error del backend en sí: el **navegador canceló** la petición a `GET /api/rutas-operativas` (por ejemplo `fetch` con `AbortController`, timeout del cliente, `useEffect` que aborta al desmontar, React Strict Mode en desarrollo, o un proxy con límite de tiempo corto).

Mientras esa petición quede **abortada**, el frontend cae al **fallback** y solo verás **una** polyline.

**Qué hacer en frontend**

- Para **`/api/rutas-operativas`** usa un timeout **largo** (recomendado **90–120 s**) o **no** pases `signal` de aborto en esa llamada concreta hasta que termine la primera respuesta válida.
- Si abortas en el `cleanup` del `useEffect`, asegúrate de **no** abortar peticiones “en vuelo” que siguen siendo la petición vigente del mismo par UE–destino (patrón: ignorar resultado si cambió la clave, en lugar de abortar siempre).
- Revisa el **proxy** (Next, Vite, nginx): muchos cortan a **10–30 s**; sube el límite para la ruta `/api/rutas-operativas` o para todo `/api/*`.

El backend puede tardar **varias decenas de segundos** en el peor caso (muchas consultas a Valhalla para armar 3 alternativas distintas en trayectos cortos).

### 2. `Access-Control-Allow-Origin` y `POST https://valhalla1.openstreetmap.de/route`

**El navegador no debe llamar a Valhalla.** Ese dominio **no** está pensado para CORS desde `http://localhost:3000`; además verás **429 Too Many Requests** si el cliente pega directo al API público.

**Qué hacer**

- **Elimina** cualquier `fetch` / `axios` desde el frontend hacia `valhalla1.openstreetmap.de` (o similar).
- Toda la ruta debe ser: **frontend → tu backend** (`/api/rutas-operativas` o `/api/ruta`) → Valhalla en servidor.

Si hoy tienes un “auxilio” tipo `mostrarRutaAuxilio` que llama a Valhalla cuando fallan operativas, **no lo uses en el navegador**; limita el auxilio a **otro endpoint del mismo backend** (o muestra error sin ruta).

### 3. Orden correcto de implementación

1. Llamar solo a **`GET /api/rutas-operativas`** (con timeout largo).
2. Si la respuesta es 200 y `total === 3`, dibujar las **tres** `coordinates`.
3. Si falla (red, 502, timeout), mostrar error o reintentar con backoff; **no** abrir Valhalla desde el cliente.

### 4. `500` en `http://localhost:3000/api/rutas-operativas` (y `BACKEND_PROXY_TARGET`)

Esa URL es el **servidor de desarrollo del frontend** (p. ej. Next.js en el puerto **3000**), no el proceso FastAPI (suele ser el puerto **8000**). El mensaje *«revisa BACKEND_PROXY_TARGET»* indica que tu frontend **reenvía** `/api/*` a otro host mediante una variable de entorno (nombre típico: `BACKEND_PROXY_TARGET` o similar).

Un **500** en `:3000` casi nunca lo genera el router de rutas de FastAPI por sí solo: lo habitual es que el **route handler / rewrite** de Next falle al hacer `fetch` al backend.

#### Checklist rápido

1. **Backend levantado** en el puerto correcto, por ejemplo:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
2. **Probar sin proxy** (desde el navegador o `curl`):
   ```text
   http://localhost:8000/api/rutas-operativas?tipo=ruta_ue_a_coordenada&ueLat=19.28491318&ueLon=-99.64152779&coordLat=19.286837&coordLon=-99.63739
   ```
   - Si aquí tarda **~1 min** pero acaba en **200**, la API está bien.
   - Si aquí ves **502** con JSON `detail`, el fallo es **Valhalla / red** hacia el backend, no Next.
3. **Variable de entorno del frontend** (Next: `.env.local` en el repo del cliente, **reiniciar** `npm run dev` tras cambiarla):
   ```env
   BACKEND_PROXY_TARGET=http://127.0.0.1:8000
   ```
   - Sin barra final (o con barra final, pero **consistente** con cómo concatenas rutas en el handler).
   - Si el valor es `http://localhost:8000` y en Docker/WSL falla, prueba `http://127.0.0.1:8000`.
4. **Logs de la terminal donde corre Next** (no solo la consola del navegador): suele aparecer `ECONNREFUSED`, `fetch failed`, URL mal formada o timeout del **servidor** Node al llamar a `:8000`.
5. **Timeout del proxy de Next** (`next dev`): sin configuración, el reenvío de `/api/*` suele cortar alrededor de **30 s** y el navegador recibe **500** aunque el backend siga trabajando. En el repo `automap-frontend` está definido **`experimental.proxyTimeout`** en `next.config.ts` (180 s), alineado con `FETCH_RUTAS_OPERATIVAS_TIMEOUT_MS` en `lib/api.ts`. Tras cambiar `next.config.ts`, **reinicia** `npm run dev` / `bun dev`.

#### Patrón recomendado en el route handler (idea)

- Leer `process.env.BACKEND_PROXY_TARGET` (o el nombre que use vuestro `api.ts`).
- `fetch(`${base}/api/rutas-operativas?${searchParams}`, { signal: AbortSignal.timeout(120_000) })` (o equivalente sin abortar antes).
- Si `fetch` lanza (red, DNS, conexión rechazada), responder **`502` o `503`** con un JSON `{ "detail": "..." }` en lugar de dejar que Next devuelva **500** vacío: así en DevTools verás la causa y no confundirás con un bug del backend Python.

#### `next.config` (rewrites) frente a Route Handler

- Con **rewrites** a `http://localhost:8000`, Next a veces delega bien el GET; igual revisa **timeouts** del servidor upstream si hay proxy intermedio.
- Con **Route Handler** (`app/api/.../route.ts`) tenéis control total del `fetch` al backend: ahí es donde más suele fallar la URL base o el timeout.

#### Código Python (este repo)

- Los errores de Valhalla en el endpoint suelen traducirse en **`502`** con `detail` en el JSON, no en **`500`**.
- Si `:8000` responde bien y `:3000` sigue en **500**, el arreglo está en el **repo del frontend** (env, handler, timeout), no en `valhalla.py`.

## Referencia de código en el repo

- Router: `app/routers/ruta.py` (`get_rutas_operativas`).
- Lógica de alternativas, correlación, perfil de trayecto corto y filtros: `app/services/valhalla.py` (`obtener_rutas`, `_urban_short_trip_params`).
- Timeout unificado rutas operativas (cliente + proxy Next): `automap-frontend/lib/rutasOperativasConfig.ts`.

---

Si tras desplegar esta versión el JSON muestra tres `coordinates` distintas y el mapa sigue mostrando una sola línea, el siguiente paso es revisar en el **repositorio del frontend** la capa que consume `rutas-operativas` (deduplicación, índice de capa o endpoint equivocado).
