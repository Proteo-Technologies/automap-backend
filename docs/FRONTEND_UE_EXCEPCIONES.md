# Frontend: excepciones UE (fuera del bbox / buffer)

Guía para implementar en el cliente la inclusión de UEs **fuera** del rectángulo de consulta, usando **categorías** (recomendado) y, opcionalmente, **UEs puntuales** (legacy).

---

## 1. Qué resuelve el backend (y qué no)

| El backend hace | El backend no hace |
|-----------------|-------------------|
| Filtra DENUE por **bbox** rectangular (`minLat`…`maxLon`) | No recibe radios en metros ni polígonos de buffer |
| Persiste **categorías de excepción por usuario** en BD | No guarda el tope `limiteExcepcionesFuera` (es solo query) |
| Al pedir UEs con `incluirExcepciones=true`, **mezcla** UEs fuera del bbox para esas categorías (hasta un tope) | No asocia excepciones a un `map_profile` concreto (son por usuario) |

---

## 2. Buffer en pantalla (ej. 500 m) y bbox

Las excepciones “fuera del buffer” en la práctica son **fuera del bbox** que envíes en `GET /api/unidades-economicas`.

- **Error frecuente:** usar el bbox de **todo el mapa visible**. Entonces “fuera” = fuera del mapa, no fuera del buffer de 500 m.
- **Recomendación:** construir el bbox a partir del **centro** y el **radio R** en metros (ej. 500):

```text
dlat = R / 111320
dlon = R / (111320 * cos(latitud_en_radianes))

minLat = lat - dlat
maxLat = lat + dlat
minLon = lon - dlon
maxLon = lon + dlon
```

“Dentro” / “fuera” es respecto a ese **rectángulo**, no a un círculo perfecto (en las esquinas puede haber puntos algo más lejos de R).

---

## 3. Persistencia: categorías de excepción (servidor)

Los checkboxes en UI **no** se guardan solos. Hay que sincronizar con la API.

### 3.1 Listar lo guardado en servidor

```http
GET /api/unidades-economicas/excepciones-por-categoria
Authorization: Bearer <access_token>
```

**Respuesta 200 (JSON):** array de objetos:

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": "…",
    "categoria": "hospitales",
    "created_at": "2026-04-15T12:00:00+00:00"
  }
]
```

- `id`: UUID necesario para **borrar** una categoría.
- `categoria`: mismo `id` string que devuelve `GET /api/unidades-economicas/categorias`.

### 3.2 Añadir una categoría

```http
POST /api/unidades-economicas/excepciones-por-categoria
Authorization: Bearer <access_token>
Content-Type: application/json

{"categoria": "hospitales"}
```

- **201:** creado. Si la misma categoría ya existía para el usuario, se devuelve ese registro sin duplicar fila (idempotente).
- **400:** categoría inválida (no está en el catálogo).
- **401:** sin token o token inválido.

### 3.3 Quitar una categoría

```http
DELETE /api/unidades-economicas/excepciones-por-categoria/<id>
Authorization: Bearer <access_token>
```

- **204:** eliminado.
- **404:** ese `id` no existe o no pertenece al usuario.

### 3.4 Algoritmo sugerido al “Guardar” en el editor

1. `GET .../excepciones-por-categoria` → conjunto actual `S_servidor` (por `categoria`).
2. Conjunto elegido en UI `S_ui` (checkboxes).
3. **POST** por cada `categoria` en `S_ui \ S_servidor`.
4. **DELETE** por cada `id` cuyo `categoria` está en `S_servidor \ S_ui` (necesitas el `id` del GET).

Así el servidor queda alineado con la UI tras cada guardado.

---

## 4. Cargar UEs en el mapa (incluyendo fuera del bbox)

### 4.1 Request

```http
GET /api/unidades-economicas?minLat=...&minLon=...&maxLat=...&maxLon=...&limit=800&incluirExcepciones=true&limiteExcepcionesFuera=3000
Authorization: Bearer <access_token>
```

| Query | Obligatorio | Descripción |
|-------|-------------|-------------|
| `minLat`, `minLon`, `maxLat`, `maxLon` | Sí | Bbox (debe coincidir con tu buffer / área de análisis). |
| `limit` | No (default 800, máx. 5000) | Tope de UEs para la parte **dentro** del bbox (reparto entre CSV si hay varios archivos). |
| `codigos`, `modoCodigos`, `archivos` | No | Mismo filtro SCIAN / capas que ya uses (ver **nota crítica** abajo). |
| `incluirExcepciones` | Para mezclar excepciones | `true` = añadir UEs extra según categorías guardadas + legacy. |
| `limiteExcepcionesFuera` | No (default **3000**, máx. **10000**) | Máximo de UEs **extra** traídas **fuera** del bbox por categorías. `0` = no traer esas extra por categoría (siguen aplicando excepciones puntuales si las hay). |

- Sin `Authorization` válido y `incluirExcepciones=true` → **401** (no puede saber qué categorías tiene el usuario).
- Sin base de datos configurada → **503** en rutas que usan excepciones.

### 4.2 Respuesta del backend

```json
{
  "data": [
    {
      "lat": 19.28,
      "lon": -99.64,
      "codigo_act": "622111",
      "nombre_act": "...",
      "nom_estab": "...",
      "categoria": "hospitales"
    },
    {
      "lat": 19.29,
      "lon": -99.63,
      "codigo_act": "622111",
      "nombre_act": "...",
      "nom_estab": "...",
      "categoria": "hospitales",
      "is_exception": true,
      "exception_reason": "categoria_fuera_bbox"
    }
  ],
  "total": 42
}
```

**Campos en cada UE (siempre):** `lat`, `lon`, `codigo_act`, `nombre_act`, `nom_estab`, `categoria`.

**Solo en filas añadidas por excepción por categoría (fuera del bbox):**

- `is_exception`: `true`
- `exception_reason`: `"categoria_fuera_bbox"`

**Solo en filas añadidas por excepción puntual (legacy):**

- `is_exception`: `true`
- `exception_reason`: `"ue_manual"`
- Puede venir `source_file` si se guardó al crear la excepción.

Las UEs que salen solo del filtro normal **dentro** del bbox **no** incluyen `is_exception` / `exception_reason` (el cliente puede tratar ausencia = no excepción).

### 4.3 Orden lógico del backend

1. UEs **dentro** del bbox (CSV + filtros) → hasta `limit` (repartido entre archivos si aplica).
2. UEs **fuera** del bbox, categorías marcadas en servidor, mismos filtros `codigos` / `archivos` → hasta `limiteExcepcionesFuera`.
3. UEs **puntuales** legacy → se añaden si no duplican clave interna (lat/lon + SCIAN + nombres).

### 4.4 Nota crítica: parámetro `codigos` (muy frecuente en bugs de frontend)

El mismo `codigos` (prefijos SCIAN en la query) se aplica **tanto** al tramo **dentro** del bbox **como** al tramo **fuera** del bbox (excepciones por categoría).

- Si enviáis `codigos` solo con los prefijos de **la categoría en excepción** (ej. solo hospitales), el backend **solo** devolverá UEs que cumplan esos prefijos **dentro** del bbox también → el resto de categorías “visibles” en la UI **no aparecerán**, aunque estén marcadas en capas.
- **Solución:** construir `codigos` como **unión** de todos los prefijos SCIAN de **todas** las categorías que el usuario quiere ver en el mapa (las 4 capas, etc.), no solo la que tiene excepción fuera del bbox.

La lógica de excepciones **no** reemplaza al filtro principal: primero se rellena el bbox con lo que permita `codigos`; después se añaden filas fuera del bbox para las categorías guardadas en servidor.

---

## 5. Tope `limiteExcepcionesFuera` en la UI

- Es **válido** mostrar un campo numérico (ej. 3000) y enviarlo como query en cada carga de UEs.
- El backend **no** guarda ese valor: si quieres recordarlo, **localStorage** u otra preferencia local está bien.
- Si **omitís** el parámetro, el servidor usa **3000** por defecto.

---

## 6. Excepciones puntuales (legacy), opcional

| Método | Ruta | Uso |
|--------|------|-----|
| `GET` | `/api/unidades-economicas/excepciones` | Listar UEs guardadas una a una |
| `POST` | `/api/unidades-economicas/excepciones` | Body: `lat`, `lon`, `codigo_act`, `nombre_act`, `nom_estab`, `categoria`, `source_file` opcional |
| `DELETE` | `/api/unidades-economicas/excepciones/{id}` | Quitar una |

Requieren Bearer. Prioridad recomendada en producto: **excepciones por categoría**; las puntuales solo para casos raros.

---

## 7. Proxy (Next, Vite, etc.)

- Reenviar `Authorization: Bearer …` hacia el backend (puerto 8000 o el que corresponda).
- Timeouts: peticiones con CSV grandes + `limiteExcepcionesFuera` alto pueden tardar varios segundos.

---

## 8. Resumen para implementación frontend

1. **Bbox** = mismo rectángulo que usa tu buffer (no el viewport completo si el buffer es local).
2. **Guardar categorías de excepción** = `GET` actual + `POST`/`DELETE` según diferencia con la UI (sección 3.4).
3. **Cargar mapa** = `GET /unidades-economicas` con `incluirExcepciones=true` + token + `limiteExcepcionesFuera` si queréis controlar el tope.
4. **Render** = usar `is_exception` / `exception_reason` si queréis otro estilo para UEs “extra fuera del área”.
