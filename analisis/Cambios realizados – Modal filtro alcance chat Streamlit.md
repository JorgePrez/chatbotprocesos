# Cambios realizados: modal de alcance al crear chat (Streamlit)

Documentación de lo implementado del lado del chatbot.

**Archivo modificado:** `chatbot_embebido_n8n_modularizado.py`  
**Fecha:** 2026-08-14

---

## Resumen

Al pulsar **Nuevo chat**, el chatbot ya no crea la conversación de inmediato cuando el usuario tiene áreas administrativas y académicas. En su lugar:

1. Se muestra un panel de selección de alcance.
2. Al confirmar, se crea el chat con el filtro elegido.
3. El mensaje de áreas y la búsqueda de la IA respetan ese filtro.
4. Si el usuario solo tiene un tipo de áreas, el chat se crea directo (sin modal).

---

## 1. Función auxiliar nueva: `fntObtenerAlcance`

Calcula códigos y texto de áreas según el filtro:

| Filtro | Resultado |
|--------|-----------|
| `TODO` | Admin + académicas, **ordenadas alfabéticamente** por `NOMBRE_MOSTRAR` |
| `ADMIN` | Solo áreas con `TIPO_ASOCIACION = CENTRO_COSTO` |
| `ACAD` | Solo áreas con `TIPO_ASOCIACION = FACULTAD` |

Retorna:

- lista de códigos (`CODIGO`)
- texto markdown con la lista de nombres para el mensaje de áreas

---

## 2. Separación de áreas tras la API

Antes se armaba una sola lista de códigos activos.

Ahora:

1. Se filtran ítems con `ACTIVO == "Y"`.
2. Se separan en:
   - `areas_admin` → `TIPO_ASOCIACION == "CENTRO_COSTO"`
   - `areas_acad` → `TIPO_ASOCIACION == "FACULTAD"`
3. Se calculan flags:
   - `tiene_admin`
   - `tiene_acad`

**Prerrequisito:** la API debe devolver `TIPO_ASOCIACION`.

---

## 3. Nuevos estados en `session_state`

| Estado | Valores | Uso |
|--------|---------|-----|
| `pendiente_filtro_nuevo_chat` | `True` / `False` | Controla si se muestra el panel de alcance |
| `filtro_alcance` | `TODO` / `ADMIN` / `ACAD` | Alcance del chat actual (default: `TODO`) |
| `codigos_activos_chat` | lista | Códigos que se envían a la IA en esa conversación |
| `areas_texto_chat` | string | Texto del mensaje de áreas del chat |
| `selector_alcance_nuevo_chat` | `TODO` / `ADMIN` / `ACAD` | Valor del radio del panel |

---

## 4. Botón **Nuevo chat** (sidebar)

### Antes
Al hacer clic se creaba el chat en Dynamo de inmediato.

### Ahora
1. Limpia mensajes.
2. No crea aún el registro en Dynamo.
3. Según permisos:

| Situación | Comportamiento |
|-----------|----------------|
| Tiene admin **y** académicas | Abre el panel (`pendiente_filtro_nuevo_chat = True`) |
| Solo admin | Crea chat directo con filtro `ADMIN` |
| Solo académicas | Crea chat directo con filtro `ACAD` |
| Ninguna área activa | Se mantiene el error existente |

---

## 5. Panel / modal de alcance

Se muestra en el área principal (contenedor con borde) cuando hay ambos tipos de áreas.

### Contenido
- Título: `Selecciona el alcance de la búsqueda`
- Texto de apoyo: `Puedes limitar la consulta a un tipo de unidad o buscar en todo el repositorio.`
- Radios:

| Texto | Valor | Default |
|-------|-------|---------|
| Buscar en todo el repositorio | `TODO` | Sí |
| Buscar solo en unidades administrativas | `ADMIN` | No |
| Buscar solo en unidades académicas | `ACAD` | No |

- Botón **Crear conversación**: confirma, crea el chat y entra a la conversación.
- Botón **Cancelar**: cierra el panel sin crear chat.

Mientras el panel está abierto:

- No se muestra `chat_input`
- No se muestra el listado de áreas del chat nuevo

---

## 6. Función `crearChatNuevo(filtro)`

Centraliza la creación del chat:

1. Calcula códigos y texto con `fntObtenerAlcance`
2. Guarda `filtro_alcance`, `codigos_activos_chat`, `areas_texto_chat`
3. Genera `chat_id` (`uuid`)
4. Guarda en Dynamo (`"nuevo chat"`, mensajes vacíos)
5. Activa `new_chat_procesos`
6. Cierra el panel (`pendiente_filtro_nuevo_chat = False`)

---

## 7. Mensaje de áreas al entrar al chat

### Antes
Listaba todas las áreas activas del usuario.

### Ahora
Usa `areas_texto_chat` según el filtro elegido:

- `ADMIN` → solo administrativas
- `ACAD` → solo académicas
- `TODO` → ambas, en orden alfabético

Texto:

```text
Puedes consultar procesos de las siguientes áreas:
- Área 1
- Área 2
```

---

## 8. Llamada a la IA

### Antes
Se pasaba `codigos_activos` (todos).

### Ahora
Se pasa `st.session_state.codigos_activos_chat`.

Así Bedrock busca solo dentro del alcance de esa conversación.

---

## 9. Reabrir chat existente (`loadChat`)

Al cargar un chat del historial:

- `filtro_alcance = "TODO"`
- Se recalculan códigos/texto con todas las áreas activas
- Se cierra cualquier panel pendiente

**Nota:** persistir el filtro en Dynamo quedó fuera de esta entrega.

---

## 10. Orden alfabético

Cuando el alcance es `TODO` (todas las áreas juntas), la lista se ordena alfabéticamente por `NOMBRE_MOSTRAR` (comparación case-insensitive con `casefold()`).

---

## 11. Qué no se modificó

- `config/model_iacatching.py`
- `config/dynamo_crud.py`
- `repositorio_procesos.php` / API
- Parámetros del iframe (`tieneTD`, `tieneTC`, etc.)
- Estilo general de la UI (sidebar, historial, chat, mensajes)

---

## 12. Flujo resultante

```
Usuario pulsa "Nuevo chat"
        │
        ├─ ¿Tiene admin Y académicas activas?
        │         │
        │         ├─ Sí → Mostrar panel con radios
        │         │         default = Todo el repositorio
        │         │         Confirmar → crear chat filtrado
        │         │         Cancelar → no crea chat
        │         │
        │         └─ NO → Crear chat directo
        │                   (ADMIN o ACAD según lo que tenga)
        │
        └─ Chat abierto
              - Mensaje de áreas según filtro
              - Búsqueda con codigos_activos_chat
              - Si TODO: áreas en orden alfabético
```

---

## 13. Checklist de aceptación

- [x] Al pulsar Nuevo chat con ambos tipos, aparece el panel con radios.
- [x] Default = Buscar en todo el repositorio.
- [x] Confirmar crea el chat con el filtro elegido.
- [x] Cancelar no crea chat.
- [x] El listado de áreas respeta el filtro.
- [x] La búsqueda de la conversación respeta el filtro.
- [x] Si solo hay un tipo activo, no aparece el panel.
- [x] Reabrir chat viejo sigue funcionando (alcance `TODO`).
- [x] Con alcance `TODO`, las áreas salen en orden alfabético.
