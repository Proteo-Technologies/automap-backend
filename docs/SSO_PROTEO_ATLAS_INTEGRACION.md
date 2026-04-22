# Integración SSO: Proteo Atlas (Supabase) ↔ Automap

Este documento resume los cambios realizados para permitir que usuarios del ERP **Proteo Atlas** (autenticación **Supabase**) inicien sesión en **Automap** (API FastAPI + frontend Next.js) con el mismo token, sin sustituir el registro/login público por correo y contraseña.

---

## Arquitectura del flujo

1. El usuario hace clic en **Ingresar con Proteo Atlas** en el frontend de Automap.
2. Se redirige al login del ERP (`/login/cgr`) con el parámetro `next` apuntando al callback de Automap.
3. Tras sesión válida en el ERP, este redirige a `http://localhost:3000/auth/proteo/callback?...` incluyendo `access_token` (JWT Supabase) y opcionalmente `returnTo`.
4. El callback de Automap llama a `POST /api/auth/sso/supabase` con ese token.
5. El backend valida el JWT, sincroniza perfil/estado desde Supabase (REST) y devuelve un **JWT local** de Automap.
6. El frontend guarda el token local y usa el resto de la API como siempre.

**Dos bases de datos:** los datos de mapas siguen en PostgreSQL de Automap; perfiles y empleados del ERP se leen desde **Supabase** vía API REST con clave de servicio.

---

## 1. Backend — `automap-backend`

### Nuevos endpoints (sin eliminar los existentes)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/auth/sso/supabase` | Recibe `{ "access_token": "<JWT Supabase>" }`, valida token, crea/enlaza usuario local, devuelve `{ access_token, token_type }` de Automap. |

Los endpoints públicos actuales **no se modificaron en contrato**:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`

### Archivos relevantes

| Archivo | Cambio |
|---------|--------|
| `app/routers/auth.py` | Endpoint SSO; enlace por `supabase_user_id` y email; sincronización de campos de usuario tras SSO. |
| `app/core/supabase_auth.py` | Validación de JWT Supabase: `HS256` (con `SUPABASE_JWT_SECRET`) y `RS256`/`ES256` (JWKS); comprobación de `iss`, `aud`, `exp`. |
| `app/core/supabase_profile_sync.py` | Lectura de `public.profiles` y `public.employees` en Supabase vía REST (`/rest/v1`). |
| `app/core/config.py` | Variables: `SUPABASE_*`, `SUPABASE_SERVICE_ROLE_KEY`, límites SSO, etc. |
| `app/models/orm.py` | Columnas `supabase_user_id`, `auth_provider` en `users`. |
| `app/schemas/auth.py` | Modelo `SupabaseSSOLogin` con `access_token`. |
| `alembic/versions/009_users_supabase_sso.py` | Migración encadenada al head existente (evitar múltiples heads). |
| `docker-compose.yml` | Paso de variables `SUPABASE_*` y `SUPABASE_SERVICE_ROLE_KEY` al servicio `backend`. |
| `.env.example` | Documentación de variables SSO. |

### Variables de entorno (backend)

| Variable | Uso |
|----------|-----|
| `SUPABASE_URL` | URL del proyecto Supabase. |
| `SUPABASE_JWT_ISSUER` | Opcional; si falta se deriva como `{SUPABASE_URL}/auth/v1`. |
| `SUPABASE_JWT_AUDIENCE` | Típicamente `authenticated`. |
| `SUPABASE_JWT_SECRET` | Obligatorio si los access tokens usan **HS256**. |
| `SUPABASE_SERVICE_ROLE_KEY` | Solo servidor: lectura de `profiles` / `employees` por REST. |

**Docker local:** dejar `DATABASE_URL` vacío en `.env` para que el entrypoint arme la URL contra el servicio `postgres` del compose (no usar `localhost` como host dentro del contenedor).

### Base de datos local (Automap)

- Tabla `users`: campos adicionales para enlace SSO y proveedor.
- Las tablas `profiles` / `employees` del ERP **no** tienen por qué existir en esta BD; la fuente es Supabase.

---

## 2. Frontend — `automap-frontend`

### Comportamiento

- Botón **Ingresar con Proteo Atlas** en el modal de login (`AuthModal`).
- Construye URL del ERP con `next=<callback Automap>` (y otros params compatibles según `lib/proteoAuth.ts`).
- Ruta **`/auth/proteo/callback`**: lee `access_token` de query o hash, llama al backend SSO, guarda JWT local y redirige según `returnTo`.

### Archivos relevantes

| Archivo | Cambio |
|---------|--------|
| `lib/apiAuth.ts` | Función `authSupabaseSSO`. |
| `context/AuthContext.tsx` | `loginWithProteoToken`. |
| `lib/proteoAuth.ts` | URLs de login/callback ERP y extracción de token de la URL. |
| `components/AuthModal.tsx` | Botón SSO en modo login. |
| `app/auth/proteo/callback/page.tsx` | Página de callback. |
| `.env.local.example` | `NEXT_PUBLIC_PROTEO_LOGIN_URL`, `NEXT_PUBLIC_PROTEO_REDIRECT_PARAM`, etc. |
| `README.md` | Notas de variables SSO. |

### Variables de entorno (frontend)

| Variable | Ejemplo local |
|----------|----------------|
| `NEXT_PUBLIC_PROTEO_LOGIN_URL` | `http://localhost:3001/login/cgr` |
| `NEXT_PUBLIC_PROTEO_REDIRECT_PARAM` | Depende del ERP; Automap puede enviar varios nombres de param. |
| `NEXT_PUBLIC_PROTEO_CALLBACK_URL` | Opcional; por defecto `{origin}/auth/proteo/callback` |

El proxy a FastAPI sigue siendo el habitual (`NEXT_PUBLIC_API_URL` vacío + `BACKEND_PROXY_TARGET`).

---

## 3. ERP — `PROTEO-ATLAS` (requerido para el botón)

Sin cambios en el ERP, el parámetro `next` llegaba a `/login/cgr` pero la página solo leía `redirect`, por lo que el usuario acababa en `/time-tracking`.

### Archivos relevantes

| Archivo | Cambio |
|---------|--------|
| `src/app/(auth)/login/cgr/page.tsx` | Lee `next` **o** `redirect`; si la URL es externa y está permitida, añade `access_token` y hace `window.location.assign`. |
| `src/lib/utils/ssoReturnUrl.ts` | Lista blanca de orígenes vía `NEXT_PUBLIC_SSO_RETURN_ORIGINS`. |
| `.env.example` | Documentación de `NEXT_PUBLIC_SSO_RETURN_ORIGINS`. |

### Variable de entorno (ERP)

| Variable | Uso |
|----------|-----|
| `NEXT_PUBLIC_SSO_RETURN_ORIGINS` | Orígenes permitidos para `next`/`redirect` externos (ej. `http://localhost:3000`). |

---

## 4. Seguridad (notas)

- **`SUPABASE_SERVICE_ROLE_KEY` y `SUPABASE_JWT_SECRET`**: secretos de servidor; no exponer al cliente.
- Pasar **`access_token` en query string** es práctico en desarrollo; en producción conviene valorar flujo con **authorization code** + PKCE y menos datos sensibles en URL.
- **`NEXT_PUBLIC_SSO_RETURN_ORIGINS`** en el ERP mitiga **open redirect**: solo se aceptan orígenes configurados.

---

## 5. Verificación rápida

1. Backend: `POST /api/auth/sso/supabase` con un `access_token` Supabase válido → `200` y JWT Automap.
2. Frontend: clic en Proteo Atlas → ERP → vuelta a `/auth/proteo/callback?...&access_token=...` → sesión en Automap.
3. ERP: con sesión ya iniciada, abrir  
   `http://localhost:3001/login/cgr?next=http://localhost:3000/auth/proteo/callback?returnTo=/`  
   y comprobar redirección a Automap con token.

---

## 6. Repositorios tocados

| Repositorio | Rol |
|-------------|-----|
| `automap-backend` | Validación JWT, usuario local, sync Supabase REST. |
| `automap-frontend` | Botón, callback, contexto de auth. |
| `PROTEO-ATLAS` | Respeto de `next`, redirect externo con token, allowlist. |

---

*Última actualización: documentación alineada con la integración SSO Proteo Atlas ↔ Automap descrita en esta conversación.*
