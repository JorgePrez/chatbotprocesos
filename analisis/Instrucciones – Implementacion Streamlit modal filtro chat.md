# Instrucciones de implementación Streamlit: modal de alcance al crear chat

Solo guía de cambios en el chatbot. **No aplicar aún.**

Archivo principal: `chatbotprocesos/chatbot_embebido_n8n_modularizado.py`  
Prerrequisito: la API ya debe devolver `TIPO_ASOCIACION` (`CENTRO_COSTO` / `FACULTAD`).

---

## Objetivo de UX

Al pulsar **Nuevo chat**:

1. No crear la conversación de inmediato.
2. Abrir una pantalla intermedia tipo **modal / panel de selección**.
3. Mostrar radios para elegir el alcance de búsqueda.
4. Default: **Buscar en todo el repositorio**.
5. Al confirmar, crear el chat con ese filtro.
6. El mensaje *“Puedes consultar procesos de las siguientes áreas:”* debe listar solo las áreas del alcance elegido.
7. Si el usuario solo tiene un tipo de áreas activas, **no mostrar el modal**; crear el chat directo.

---

## 1. Comportamiento del modal

### Cuándo se muestra

Solo si el usuario tiene áreas activas de **ambos** tipos:

- al menos una con `TIPO_ASOCIACION = CENTRO_COSTO` y `ACTIVO = Y`
- al menos una con `TIPO_ASOCIACION = FACULTAD` y `ACTIVO = Y`

### Contenido del modal

Título sugerido:

**Selecciona el alcance de la búsqueda**

Texto de apoyo (opcional):

Puedes limitar la consulta a un tipo de unidad o buscar en todo el repositorio.

### Radio buttons (3 opciones)

| Orden | Texto | Valor interno | Default |
|-------|--------|---------------|---------|
| 1 | Buscar en todo el repositorio | `TODO` | Sí |
| 2 | Buscar solo en unidades administrativas | `ADMIN` | No |
| 3 | Buscar solo en unidades académicas | `ACAD` | No |

Usar `st.radio` (Streamlit no tiene modal nativo; se simula con un panel/bloque en el área principal o con `st.dialog` si la versión lo permite).

### Botones del modal

- **Crear conversación** (principal): confirma el radio, crea el chat y entra a la conversación.
- **Cancelar** (opcional): cierra el panel y vuelve a la pantalla inicial sin crear chat.

### Cuándo NO se muestra

| Situación | Qué hacer |
|-----------|-----------|
| Solo áreas administrativas activas | Crear chat directo con filtro `ADMIN` |
| Solo áreas académicas activas | Crear chat directo con filtro `ACAD` |
| Ninguna área activa | Error actual: sin áreas disponibles |

---

## 2. Estados nuevos en `session_state`

| Estado | Valores | Para qué |
|--------|---------|----------|
| `pendiente_filtro_nuevo_chat` | `True` / `False` | Controla si se muestra el modal |
| `filtro_alcance` | `TODO` / `ADMIN` / `ACAD` | Alcance del chat actual |
| `codigos_activos_chat` | lista de códigos | Filtro que se manda a la IA |
| `areas_texto_chat` | string | Texto del mensaje de áreas del chat |

Default de `filtro_alcance`: `TODO`.

---

## 3. Cambios por sección del archivo

### 3.1 Después de cargar la respuesta de la API

Hoy se arma una sola lista de códigos activos.

Cambiar a:

1. Filtrar ítems con `ACTIVO == "Y"`.
2. Separar:
   - `areas_admin` ? `TIPO_ASOCIACION == "CENTRO_COSTO"`
   - `areas_acad` ? `TIPO_ASOCIACION == "FACULTAD"`
3. Guardar flags:
   - `tiene_admin`
   - `tiene_acad`

### 3.2 Función auxiliar (recomendada)

Crear algo como `fntObtenerAlcance(filtro, areas_admin, areas_acad)` que devuelva:

- lista de códigos
- texto markdown/lista de nombres para el mensaje de áreas

Reglas:

- `TODO` ? admin + académicas
- `ADMIN` ? solo admin
- `ACAD` ? solo académicas

### 3.3 Botón **Nuevo chat** (sidebar)

Hoy crea el chat al instante.

Cambiar a:

1. Al hacer clic:
   - limpiar mensajes
   - poner `pendiente_filtro_nuevo_chat = True`
   - **no** crear todavía el registro en Dynamo
2. Si solo hay un tipo activo:
   - setear `filtro_alcance` automáticamente
   - calcular códigos/texto
   - crear chat en Dynamo
   - `new_chat_procesos = True`
   - `pendiente_filtro_nuevo_chat = False`
3. Si hay ambos tipos:
   - solo mostrar el modal (paso siguiente)

### 3.4 Render del modal

Cuando `pendiente_filtro_nuevo_chat == True` y hay ambos tipos:

Mostrar en el área principal (o `st.dialog`):

1. Título
2. `st.radio` con las 3 opciones (`index=0` = todo el repositorio)
3. Botón **Crear conversación**
4. Botón **Cancelar** (opcional)

Al confirmar **Crear conversación**:

1. Leer la opción del radio y mapear a `TODO` / `ADMIN` / `ACAD`
2. Guardar `filtro_alcance`
3. Calcular `codigos_activos_chat` y `areas_texto_chat`
4. Generar `chat_id` (`uuid`)
5. Guardar chat en Dynamo (`"nuevo chat"`, mensajes vacíos)
6. `new_chat_procesos = True`
7. `pendiente_filtro_nuevo_chat = False`
8. `st.rerun()` si hace falta

Mientras el modal esté abierto:

- No mostrar aún el `chat_input`
- No mostrar todavía el listado de áreas del chat nuevo

### 3.5 Mensaje de áreas al entrar al chat

Hoy:

```text
Puedes consultar procesos de las siguientes áreas:
- ...
```

Cambiar para usar `areas_texto_chat` (según el filtro elegido), no todas las áreas del usuario.

Ejemplos:

- Si eligió administrativas ? solo nombres admin
- Si eligió académicas ? solo nombres académicos
- Si eligió todo ? ambos

### 3.6 Llamada a la IA

Hoy se pasa `codigos_activos` (todos).

Cambiar a pasar `st.session_state.codigos_activos_chat`.

Así Bedrock solo busca en el alcance de esa conversación.

### 3.7 Reabrir chat existente (esta entrega)

Al cargar un chat del historial (`loadChat`):

- Usar `filtro_alcance = "TODO"`
- Recalcular códigos con todas las áreas activas del usuario

Persistir el filtro en Dynamo queda fuera de esta entrega.

---

## 4. Flujo completo (resumen)

```
Usuario pulsa "Nuevo chat"
        ?
        ?? ¿Tiene admin Y académicas activas?
        ?         ?
        ?         ?? SÍ ? Mostrar modal con radios
        ?         ?         default = Todo el repositorio
        ?         ?         Confirmar ? crear chat filtrado
        ?         ?
        ?         ?? NO ? Crear chat directo
        ?                   (ADMIN o ACAD según lo que tenga)
        ?
        ?? Chat abierto
              - Mensaje de áreas según filtro
              - Búsqueda con codigos_activos_chat
```

---

## 5. Textos sugeridos (UI)

### Modal

- Título: `Selecciona el alcance de la búsqueda`
- Radio 1: `Buscar en todo el repositorio`
- Radio 2: `Buscar solo en unidades administrativas`
- Radio 3: `Buscar solo en unidades académicas`
- Botón: `Crear conversación`
- Cancelar: `Cancelar`

### Chat nuevo

```text
Puedes consultar procesos de las siguientes áreas:
- Área 1
- Área 2
```

(según filtro)

---

## 6. Qué no modificar en esta entrega

- `config/model_iacatching.py`
- `config/dynamo_crud.py`
- `repositorio_procesos.php`
- Parámetros del iframe (`tieneTD`, `tieneTC`, etc.)

---

## 7. Checklist de aceptación (Streamlit)

- [ ] Al pulsar Nuevo chat con ambos tipos, aparece el panel/modal con radios.
- [ ] Default = Buscar en todo el repositorio.
- [ ] Confirmar crea el chat con el filtro elegido.
- [ ] Cancelar no crea chat (si se implementa cancelar).
- [ ] El listado de áreas respeta el filtro.
- [ ] La búsqueda de la conversación respeta el filtro.
- [ ] Si solo hay un tipo activo, no aparece el modal.
- [ ] Reabrir chat viejo sigue funcionando.

---

## 8. Archivo a editar

| Archivo | Qué implementar |
|---------|-----------------|
| `chatbotprocesos/chatbot_embebido_n8n_modularizado.py` | Modal/radios, estados, filtro de códigos y mensaje de áreas |

Punto de entrada: este archivo. El resto del stack de IA se deja igual.
