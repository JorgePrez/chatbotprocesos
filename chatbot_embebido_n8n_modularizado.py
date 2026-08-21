import streamlit as st
import config.dynamo_crud as DynamoDatabase
import uuid
from config.model_iacatching import run_procesos_chain 
import requests
import base64
import json

from dotenv import load_dotenv
from langsmith import traceable
from langsmith import Client

#from streamlit_feedback import streamlit_feedback

from langsmith.run_helpers import get_current_run_tree

#from streamlit_feedback import streamlit_feedback

#from langchain_core.callbacks import collect_runs



from streamlit.components.v1 import html

import streamlit.components.v1 as components



# Cargar variables de entorno
load_dotenv()
##load_dotenv(override=True)
client = Client()

import os
# Healthcheck endpoint simulado
if st.query_params.get("check") == "1":
    st.markdown("OK")
    st.stop()


def fntDecodificarPayloadChatbot(payload_b64):
    """Decodifica el query param p = base64 URL-safe(JSON) enviado por repositorio_procesos.php."""
    if not payload_b64:
        return {}

    padding = "=" * (-len(payload_b64) % 4)
    raw = base64.urlsafe_b64decode(payload_b64 + padding)
    data = json.loads(raw.decode("utf-8"))
    return data if isinstance(data, dict) else {}


def fntObtenerUrlApi(servidor):
    """
    Decide la API según url_request:
    - C = compras (pruebas)
    - I = intranet (producción)
    - L = localhost (pruebas locales)
    """
    if servidor == "I":
        return "https://intranet.ufm.edu/repositorio_procesos_api.php"
    if servidor == "L":
        return "http://localhost/repositorio_procesos_api.php"
    # Default / C = compras
    return "https://compras135.ufm.edu/repositorio_procesos_api.php"


def fntObtenerAlcance(filtro, areas_admin, areas_acad):
    if filtro == "ADMIN":
        areas_seleccionadas = areas_admin
    elif filtro == "ACAD":
        areas_seleccionadas = areas_acad
    else:
        areas_seleccionadas = sorted(
            areas_admin + areas_acad,
            key=lambda item: (item.get("NOMBRE_MOSTRAR") or "").casefold()
        )

    codigos = [item["CODIGO"] for item in areas_seleccionadas]
    nombres = [item["NOMBRE_MOSTRAR"] for item in areas_seleccionadas]
    areas_texto = "\n".join([f"- {nombre}" for nombre in nombres])

    return codigos, areas_texto



def invoke_with_retries_procesos(run_chain_fn, question, history, config=None, max_retries=10):
    attempt = 0
    warning_placeholder = st.empty()

    
    with st.chat_message("assistant"):
        response_placeholder = st.empty()

        while attempt < max_retries:
            try:
                #print(f"{attempt + 1} de {max_retries}")
                full_response = ""

                for chunk in run_chain_fn(question, history):
                    if 'response' in chunk:
                        full_response += chunk['response']
                        response_placeholder.markdown(full_response)

                response_placeholder.markdown(full_response)

                st.session_state.messages_procesos.append({
                    "role": "assistant",
                    "content": full_response,
                })

                DynamoDatabase.edit(
                    st.session_state.chat_id_procesos,
                    st.session_state.messages_procesos,
                    st.session_state.username
                )

                if DynamoDatabase.getNameChat(st.session_state.chat_id_procesos, st.session_state.username) == "nuevo chat":
                    DynamoDatabase.editName(st.session_state.chat_id_procesos, question, st.session_state.username)
                    st.rerun()

                warning_placeholder.empty()
                return

            except Exception as e:
                attempt += 1
                if attempt == 1:
                    warning_placeholder.markdown("⌛ Esperando generación de respuesta...", unsafe_allow_html=True)
                print(f"Error inesperado en reintento {attempt}: {str(e)}")
                if attempt == max_retries:
                    warning_placeholder.markdown("⚠️ **No fue posible generar la respuesta, vuelve a intentar.**", unsafe_allow_html=True)


def main():

    query_params = st.query_params

    # Formato actual de repositorio_procesos.php: ?p=<base64url(json)>
    # Compatibilidad: también acepta user_id / id_persona / url_request sueltos
    payload_b64 = query_params.get("p", "")
    user_id = ""
    persona_id = ""
    servidor = ""

    if payload_b64:
        try:
            data_payload = fntDecodificarPayloadChatbot(payload_b64)
            user_id = data_payload.get("user_id", "") or ""
            persona_id = data_payload.get("id_persona", "") or ""
            servidor = data_payload.get("url_request", "") or ""
        except Exception:
            st.error("⚠️ Payload de acceso inválido.")
            st.stop()
    else:
        user_id = query_params.get("user_id", "")
        persona_id = query_params.get("id_persona", "")
        servidor = query_params.get("url_request", "")


    if user_id:
        st.session_state.username =session = user_id  # Guardarlo en la sesión 
        st.session_state.persona_id = persona_id  # Guardarlo en la sesión
        st.session_state.servidor = servidor
        st.sidebar.info(f"Usuario: {st.session_state.username}")

        api_url = fntObtenerUrlApi(st.session_state.servidor)
        api_token = os.getenv("REPOSITORIO_API_TOKEN", "").strip()

        if not api_token:
            st.error("⚠️ Falta REPOSITORIO_API_TOKEN en el archivo .env")
            st.stop()

        # La API calcula el alcance en servidor; no se envían tieneTD/tieneTC
        payload = {
            "centroCostosPermisos": "1",
            "id_persona": st.session_state.persona_id,
        }
         

        # Encabezados para la solicitud (form-data usa `x-www-form-urlencoded`)
        # Agregar más encabezados, importante, sino se tiene User-Agent da forbidden
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "X-API-Token": api_token
        }

        # Hacer el POST automáticamente cuando hay un user_id
        with st.spinner("Obteniendo permisos..."):
            try:
                response = requests.post(
                    api_url,
                    data=payload,
                    headers=headers,
                    timeout=30
                )
            except requests.Timeout:
                st.error("⚠️ Tiempo de espera agotado al consultar permisos.")
                st.caption(f"API: {api_url}")
                st.stop()
            except requests.RequestException as e:
                st.error("⚠️ No se pudo conectar con la API de permisos.")
                st.caption(f"API: {api_url}")
                st.text(str(e))
                st.stop()

  
        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError:
                st.error("⚠️ La API no devolvió JSON válido.")
                st.caption(f"API: {api_url}")
                st.text(response.text[:1000])
                st.stop()

            # Si la API responde error de negocio, no seguir como lista de áreas
            if isinstance(data, dict) and data.get("error"):
                st.error(f"⚠️ {data.get('error')}")
                st.caption(f"API: {api_url}")
                st.stop()

            if isinstance(data, dict) and data.get("STATUS") == "ERROR":
                st.error(f"⚠️ {data.get('ERROR', {}).get('MESSAGE', 'Error de API')}")
                st.caption(f"API: {api_url}")
                st.stop()

            if not isinstance(data, list):
                st.error("⚠️ Respuesta inesperada de la API de permisos.")
                st.caption(f"API: {api_url}")
                st.json(data)
                st.stop()

            # Guardar el JSON completo de los permisos en `st.session_state`
            st.session_state.centros_costos = data  
            #st.json(data)

        else:
            st.error(f"⚠️ Acceso denegado: {response.status_code}")
            st.caption(f"API: {api_url}")
            st.text(response.text)  # Mostrar el error en texto si lo hay
            st.stop()


    else:

        st.error("⚠️ Acceso denegado.")
        st.stop()  # Detiene la ejecución de Streamlit
    

    if "centros_costos" in st.session_state and st.session_state.centros_costos:
            # Filtrar solo los centros que tienen "ACTIVO": "Y"
            areas_activas = [item for item in st.session_state.centros_costos if item.get("ACTIVO") == "Y"]
            areas_admin = [item for item in areas_activas if item.get("TIPO_ASOCIACION") == "CENTRO_COSTO"]
            areas_acad = [item for item in areas_activas if item.get("TIPO_ASOCIACION") == "FACULTAD"]
            tiene_admin = bool(areas_admin)
            tiene_acad = bool(areas_acad)
            codigos_activos, centros_texto = fntObtenerAlcance("TODO", areas_admin, areas_acad)


            if not codigos_activos:
                st.error("⚠️ No tienes áreas disponibles .")
                st.stop()
        
    else:
            centros_texto = "No tienes áreas disponibles."
            st.stop()


    titulo = "Asistente de Procesos UFM 🔗"
    mensaje_nuevo_chat = "Nuevo chat"

    st.subheader(titulo, divider='rainbow')


            ##st.info(f"Puedes consultar procesos de las siguientes áreas:\n{centros_texto}")

    #    "Mi misión es facilitarte el acceso a la información y guiarte a través de los procesos de la manera más eficiente posible.\n\n"
    #    "---\n"

    descripcion_chatbot = (
    "Soy tu asistente sobre procesos de la UFM, ¿En qué puedo apoyarte?\n"
    "- Responder consultas sobre procesos específicos, guiándote paso a paso.\n"
    "- Mostrar una lista de procesos relacionados y ayudarte a encontrar el proceso adecuado.\n"
    "- Proporcionar enlaces directos a documentos y flujogramas relevantes.\n"
    "- Aclarar dudas y solicitar más detalles para asegurar que obtengas la mejor respuesta posible.\n"
    "- Ofrecer información sobre tiempos estimados, participantes y aspectos clave de cada paso de un proceso.\n\n"
    "Mi misión es facilitarte el acceso a la información y guiarte a través de los procesos de la manera más eficiente posible.\n\n"
)  

    descripcion_chatbot_centro_costos = (
    "Soy tu asistente sobre procesos de la UFM, ¿En qué puedo apoyarte?\n"
    "- Responder consultas sobre procesos específicos, guiándote paso a paso.\n"
    "- Mostrar una lista de procesos relacionados y ayudarte a encontrar el proceso adecuado.\n"
    "- Proporcionar enlaces directos a documentos y flujogramas relevantes.\n"
    "- Aclarar dudas y solicitar más detalles para asegurar que obtengas la mejor respuesta posible.\n"
    "- Ofrecer información sobre tiempos estimados, participantes y aspectos clave de cada paso de un proceso.\n\n"
    "Mi misión es facilitarte el acceso a la información y guiarte a través de los procesos de la manera más eficiente posible.\n\n"
    "---\n"
    f"Puedes consultar procesos de las siguientes áreas:\n{centros_texto}"
    )  

    #st.info(f"Puedes consultar procesos de las siguientes áreas:\n{centros_texto}")


    if "messages_procesos" not in st.session_state:
        st.session_state.messages_procesos = []
    if "chat_id_procesos" not in st.session_state:
        st.session_state.chat_id_procesos = ""
    if "new_chat_procesos" not in st.session_state:
        st.session_state.new_chat_procesos = False
    if "pendiente_filtro_nuevo_chat" not in st.session_state:
        st.session_state.pendiente_filtro_nuevo_chat = False
    if "filtro_alcance" not in st.session_state:
        st.session_state.filtro_alcance = "TODO"
    if "codigos_activos_chat" not in st.session_state:
        st.session_state.codigos_activos_chat = codigos_activos
    if "areas_texto_chat" not in st.session_state:
        st.session_state.areas_texto_chat = centros_texto

    def cleanChat():
        st.session_state.new_chat_procesos = False

    def cleanMessages():
        st.session_state.messages_procesos = []

    def loadChat(chat, chat_id):
        st.session_state.new_chat_procesos = True
        st.session_state.messages_procesos = chat
        st.session_state.chat_id_procesos = chat_id
        st.session_state.pendiente_filtro_nuevo_chat = False
        st.session_state.filtro_alcance = "TODO"
        st.session_state.codigos_activos_chat, st.session_state.areas_texto_chat = fntObtenerAlcance(
            "TODO", areas_admin, areas_acad
        )

    def crearChatNuevo(filtro):
        codigos, areas_texto = fntObtenerAlcance(filtro, areas_admin, areas_acad)
        st.session_state.filtro_alcance = filtro
        st.session_state.codigos_activos_chat = codigos
        st.session_state.areas_texto_chat = areas_texto
        st.session_state.chat_id_procesos = str(uuid.uuid4())
        DynamoDatabase.save(st.session_state.chat_id_procesos, session, "nuevo chat", [])
        st.session_state.new_chat_procesos = True
        st.session_state.messages_procesos = []
        st.session_state.pendiente_filtro_nuevo_chat = False

    with st.sidebar:

        if st.button(mensaje_nuevo_chat, icon=":material/add:", use_container_width=True):
            cleanMessages()
            st.session_state.new_chat_procesos = False
            st.session_state.chat_id_procesos = ""
            st.session_state.selector_alcance_nuevo_chat = "TODO"

            if tiene_admin and tiene_acad:
                st.session_state.pendiente_filtro_nuevo_chat = True
            elif tiene_admin:
                crearChatNuevo("ADMIN")
            elif tiene_acad:
                crearChatNuevo("ACAD")

        datos = DynamoDatabase.getChats(session)

        if datos:
            for item in datos:
                chat_id = item["SK"].split("#")[1]
                if f"edit_mode_{chat_id}" not in st.session_state:
                    st.session_state[f"edit_mode_{chat_id}"] = False

                with st.container():
                    c1, c2, c3 = st.columns([8, 1, 1])

                    c1.button(f"  {item['Name']}", type="tertiary", key=f"id_{chat_id}", on_click=loadChat,
                              args=(item["Chat"], chat_id), use_container_width=True)

                    c2.button("", icon=":material/edit:", key=f"edit_btn_{chat_id}", type="tertiary", use_container_width=True,
                              on_click=lambda cid=chat_id: st.session_state.update(
                                  {f"edit_mode_{cid}": not st.session_state[f"edit_mode_{cid}"]}))

                    c3.button("", icon=":material/delete:", key=f"delete_{chat_id}", type="tertiary", use_container_width=True,
                              on_click=lambda cid=chat_id: (
                                  DynamoDatabase.delete(cid, session),
                                  st.session_state.update({
                                      "messages_procesos": [],
                                      "chat_id_procesos": "",
                                      "new_chat_procesos": False
                                  }) if st.session_state.get("chat_id_procesos") == cid else None,
                              ))

                    if st.session_state[f"edit_mode_{chat_id}"]:
                        new_name = st.text_input("Nuevo nombre de chat:", value=item["Name"], key=f"rename_input_{chat_id}")
                        if st.button("✅ Guardar nombre", key=f"save_name_{chat_id}"):
                            DynamoDatabase.editNameManual(chat_id, new_name, session)
                            st.session_state[f"edit_mode_{chat_id}"] = False
                            st.rerun()

                st.markdown('<hr style="margin-top:4px; margin-bottom:4px;">', unsafe_allow_html=True)
        else:
            st.caption("No tienes conversaciones guardadas.")

    if st.session_state.pendiente_filtro_nuevo_chat and tiene_admin and tiene_acad:
        with st.container(border=True):
            st.subheader("Selecciona el alcance de la búsqueda")
            st.write("Puedes limitar la consulta a un tipo de unidad o buscar en todo el repositorio.")

            filtro_seleccionado = st.radio(
                "Alcance de búsqueda",
                options=["TODO", "ACAD", "ADMIN"],
                format_func=lambda opcion: {
                    "TODO": "Buscar en todo el repositorio",
                    "ACAD": "Buscar solo en unidades académicas",
                    "ADMIN": "Buscar solo en unidades administrativas"
                }[opcion],
                index=0,
                key="selector_alcance_nuevo_chat"
            )

            columna_crear, columna_cancelar = st.columns(2)

            if columna_crear.button("Crear conversación", type="primary", use_container_width=True):
                crearChatNuevo(filtro_seleccionado)
                st.rerun()

            if columna_cancelar.button("Cancelar", use_container_width=True):
                st.session_state.pendiente_filtro_nuevo_chat = False
                st.session_state.new_chat_procesos = False
                st.session_state.chat_id_procesos = ""
                st.rerun()

    elif st.session_state.new_chat_procesos:

        if not st.session_state.messages_procesos:
            ##st.info(descripcion_chatbot_centro_costos) 
            st.info(f"Puedes consultar procesos de las siguientes áreas:\n{st.session_state.areas_texto_chat}")
                        
    


        for message in st.session_state.messages_procesos:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        prompt = st.chat_input("Puedes escribir aquí...")

        

        if prompt:
            st.session_state.messages_procesos.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

           # invoke_with_retries_procesos(run_procesos_chain, prompt, st.session_state.messages_procesos)
            invoke_with_retries_procesos(
                lambda q, h: run_procesos_chain(q, h, st.session_state.codigos_activos_chat),
                prompt,
                st.session_state.messages_procesos
            )

       

    else:
        #st.info("Puedes crear o seleccionar un chat existente")
        #st.write(descripcion_chatbot)
        st.info("Haz clic en '✚ Nuevo chat' para iniciar una nueva conversación , o selecciona un chat existente")
        st.divider()
        st.info(descripcion_chatbot)
        ##st.info(f"Puedes consultar procesos de las siguientes áreas:\n{centros_texto}")




if __name__ == "__main__":
    main()
