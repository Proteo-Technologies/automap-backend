# Frontend: integración de registro de usuarios (actualizado)

Este documento describe cómo debe integrarse el formulario de registro con el backend después de los cambios de control de usuarios.

## Objetivo

- Endurecer el alta de usuarios (ya no basta correo + contraseña).
- Evitar creación automática de mapas por defecto al registrarse.
- Alinear validaciones frontend/backend para reducir errores de UX.

## Endpoint

- Método: `POST`
- Ruta: `/api/auth/register`
- Auth: no requiere token

Ejemplo base URL local:

- `http://localhost:8000/api/auth/register`

## Payload requerido

Ahora el backend exige todos estos campos:

- `email` (email válido)
- `password` (mínimo 8, máximo 128 y robusta)
- `confirm_password` (debe coincidir exactamente con `password`)
- `first_name` (primer nombre)
- `middle_name` (segundo nombre, opcional)
- `last_name` (primer apellido)
- `second_last_name` (segundo apellido, opcional)
- `organization` (organización/empresa)
- `phone` (teléfono)

Ejemplo:

```json
{
  "email": "usuario@empresa.com",
  "password": "Segura#2026",
  "confirm_password": "Segura#2026",
  "first_name": "María",
  "middle_name": "Fernanda",
  "last_name": "López",
  "second_last_name": "García",
  "organization": "Protección Civil Municipal",
  "phone": "+525512345678"
}
```

## Reglas de validación backend

### `password`

Debe cumplir todas:

- al menos una minúscula
- al menos una mayúscula
- al menos un número
- al menos un símbolo (carácter no alfanumérico)
- longitud entre 8 y 128

Si no cumple, backend responde error de validación.

### `phone`

- Solo dígitos, con `+` opcional al inicio.
- Longitud efectiva entre 10 y 15 dígitos.
- Ejemplos válidos:
  - `5512345678`
  - `+525512345678`

### `first_name`, `middle_name`, `last_name`, `second_last_name` y `organization`

- Se normalizan con `trim`.
- `middle_name` y `second_last_name` son opcionales.
- El resto deben ser textos no vacíos y con longitud válida.

### `confirm_password`

- Debe coincidir con `password`.
- Se valida también en backend (además de la validación cliente recomendada).

## Respuesta esperada (201)

El backend devuelve el usuario creado:

```json
{
  "id": "uuid",
  "email": "usuario@empresa.com",
  "first_name": "María",
  "middle_name": "Fernanda",
  "last_name": "López",
  "second_last_name": "García",
  "organization": "Protección Civil Municipal",
  "phone": "+525512345678",
  "created_at": "2026-04-17T20:00:00.000000+00:00"
}
```

## Errores frecuentes a manejar en frontend

- `409 Conflict`: ya existe una cuenta con ese correo.
- `422 Unprocessable Entity`: payload inválido (campo faltante o formato inválido).
- `503 Service Unavailable`: falla de base de datos/servicio.

Recomendación UX:

- Mostrar mensajes por campo cuando sea `422`.
- En `409`, mostrar mensaje claro: "Este correo ya está registrado".
- No ocultar errores en un mensaje genérico único.

## Cambio importante de comportamiento

- En registro **ya no** se crean tipos de mapa por defecto automáticamente.
- Si el frontend esperaba mapas iniciales al entrar por primera vez, ahora debe contemplar estado vacío y guiar al usuario a crear su primer tipo de mapa manualmente.

## Checklist de implementación frontend

- Actualizar formulario de registro con:
  - correo
  - contraseña robusta
  - confirmar contraseña
  - primer nombre
  - segundo nombre (opcional)
  - primer apellido
  - segundo apellido (opcional)
  - organización
  - teléfono
- Enviar exactamente esos campos a `POST /api/auth/register`.
- Ajustar validaciones cliente para que coincidan con backend.
- Manejar `409`, `422` y `503` con mensajes diferenciados.
- Considerar flujo post-registro sin mapas por defecto.

