#################################

import boto3
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableParallel
from langchain_core.output_parsers import StrOutputParser
from langchain_aws import ChatBedrock, AmazonKnowledgeBasesRetriever
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import StreamlitChatMessageHistory
import streamlit as st
from operator import itemgetter
from langchain_core.prompts import MessagesPlaceholder
import botocore.exceptions  # Importamos excepciones específicas de Boto3
from typing import List, Dict
from pydantic import BaseModel  ##Importante esto a veces no es compatible
from langchain.schema import Document
from langchain.schema.runnable import RunnableLambda
from langchain_community.chat_message_histories import DynamoDBChatMessageHistory
import requests

#from langchain_openai.chat_models import ChatOpenAI

from collections import defaultdict
from langchain.schema import Document  # Asegúrate de importar Document si es necesario
from dotenv import load_dotenv
from langsmith import traceable
from langsmith import Client

#from streamlit_feedback import streamlit_feedback

from langsmith.run_helpers import get_current_run_tree

from streamlit_feedback import streamlit_feedback

from langchain.callbacks import collect_runs



from langsmith.run_helpers import get_current_run_tree


# Cargar variables de entorno
load_dotenv()



client = Client()


class Citation(BaseModel):
    page_content: str
    metadata: Dict

def extract_citations(response: List[Dict]) -> List[Citation]:
    return [Citation(page_content=doc.page_content, metadata=doc.metadata ) for doc in response]

# ------------------------------------------------------
# S3 Presigned URL, esto permite realizar descargar del documento

def create_presigned_url(bucket_name: str, object_name: str, expiration: int = 300) -> str:
    """Generate a presigned URL to share an S3 object"""
    s3_client = boto3.client('s3')
    try:
        response = s3_client.generate_presigned_url('get_object',
                                                    Params={'Bucket': bucket_name,
                                                            'Key': object_name},
                                                    ExpiresIn=expiration)
    except NoCredentialsError:
        st.error("AWS credentials not available")
        return ""
    return response

def parse_s3_uri(uri: str) -> tuple:
    """Parse S3 URI to extract bucket and key"""
    parts = uri.replace("s3://", "").split("/")
    bucket = parts[0]
    key = "/".join(parts[1:])
    return bucket, key


# Configuración de Bedrock
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")
#TODO: model ID

model_id = "anthropic.claude-3-haiku-20240307-v1:0"
# An error occurred (ThrottlingException) when calling the InvokeModelWithResponseStream operation (reached max retries: 4): Too many tokens, please wait before trying again.
#model_id="anthropic.claude-3-sonnet-20240229-v1:0" ##Por ejemplo este es más tardado
#model_id="anthropic.claude-3-5-haiku-20241022-v1:0" ##3.5 haiku no esta disponible on demand
#model_id= "anthropic.claude-3-5-sonnet-20241022-v2:0"      #Claude 3.5 Sonnet v2, mismo caso anterior
#model_id= "anthropic.claude-3-5-sonnet-20240620-v1:0"  ##Claude 3.5 Sonnet v1, si responde más tardado..., si funciona en este entorno
# importante encontrar cuales son los otros limites por modelo


model_kwargs = {
    "max_tokens": 4096,
    "temperature": 0.0,
    "top_k": 250,
    "top_p": 1,
    "stop_sequences": ["\n\nHuman"],
}


#inference_profile = "us.meta.llama3-2-3b-instruct-v1:0"

inference_profile1="us.anthropic.claude-3-5-haiku-20241022-v1:0"
inference_profile="us.anthropic.claude-3-haiku-20240307-v1:0"

# us.meta.llama3-2-11b-instruct-v1:0

model_kwargs2 = {
    "max_tokens": 4096,
    "temperature": 0.0,
}
# Generador de respuesta ChatBedrock:
llmClaude = ChatBedrock(
    client=bedrock_runtime,
    model_id=inference_profile,
    model_kwargs=model_kwargs,
)




# Función que genera la configuración completa del retriever de la base de conocimientos
def generar_configuracion_retriever_new():
    # Verificar si `st.session_state.centros_costos` existe y tiene datos
    if "centros_costos" in st.session_state and st.session_state.centros_costos:
        # Obtener los códigos de centros de costos activos (donde "ACTIVO" == "Y")
        activas = [cc["CODIGO"] for cc in st.session_state.centros_costos if cc["ACTIVO"] == "Y"]
    else:
        activas = []  # Si no hay datos, la lista queda vacía

        
    #print(activas)

    # Construir la configuración base
    config = {
        "vectorSearchConfiguration": {
            "numberOfResults": 100  # Máximo 100
        }
    }

    # Aplicar filtro solo si hay centros de costos activos
    if activas:
        config["vectorSearchConfiguration"]["filter"] = {
            "in": {
                "key": "codigo_area",
                "value": activas
            }
        }

    #print(config)

    return config




# Función para recuperar y depurar el contexto
def obtener_contexto(inputs, retriever):
    """
    Función que recibe un retriever como parámetro para obtener los documentos relevantes.
    """
    question = inputs["question"]  # Extraer la pregunta
    documentos = retriever.invoke(question)  # Obtener documentos relevantes

    # Diccionario para agrupar contenido por 'identificador_proceso'
    procesos_agrupados = defaultdict(list)

    # Iterar sobre los documentos recuperados
    for doc in documentos:
        # Extraer los metadatos y el identificador
        source_metadata = doc.metadata.get('source_metadata', {})
        identificador = source_metadata.get('identificador_proceso', 'Sin ID')

        # Agrupar el contenido del documento bajo el mismo identificador
        procesos_agrupados[identificador].append(doc.page_content)

    # Crear una nueva lista de Documentos con contenido concatenado por identificador_proceso
    documentos_concatenados = []
    for identificador, contenidos in procesos_agrupados.items():
        # Concatenar los contenidos
        contenido_concatenado = "\n".join(contenidos)

        # Tomar los metadatos y el score del primer documento con este identificador
        doc_base = next(
            (doc for doc in documentos if doc.metadata.get('source_metadata', {}).get('identificador_proceso') == identificador),
            None
        )

        if doc_base:
            metadatos_base = doc_base.metadata  # Metadatos del primer documento
            score_base = doc_base.metadata.get('score', 0)  # Score del primer documento
        else:
            metadatos_base = {}
            score_base = 0

        # Incluir el score en los metadatos base
        metadatos_base['score'] = score_base

        # Crear un nuevo objeto Document con el contenido concatenado
        documento_concatenado = Document(
            metadata=metadatos_base,
            page_content=contenido_concatenado
        )

        # Agregar el documento a la lista final
        documentos_concatenados.append(documento_concatenado)

    return documentos_concatenados  # Devolver los documentos concatenados


# Crear el pipeline con depuración, ahora requiere un retriever al ser llamado
def crear_context_pipeline(retriever):
    return RunnableLambda(lambda inputs: obtener_contexto(inputs, retriever))


# Nombre de la tabla en DynamoDB
table_name = "SessionTable"


# Función para crear el prompt dinámico
def create_prompt_template(system_prompt):
    return ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{question}")
        ]
    )

# Chain con historial de mensajes
def create_chain_with_history(retriever,system_prompt):
    """
    Función que crea el chain con historial de mensajes y requiere un retriever.
    """
    prompt = create_prompt_template(system_prompt)

    chain = (
        RunnableParallel({
            "context": crear_context_pipeline(retriever),  # Usamos la función que crea el pipeline con retriever
            "question": itemgetter("question"),
            "history": itemgetter("history"),
        })
        .assign(response=prompt | llmClaude | StrOutputParser())
        .pick(["response", "context"])
    )

    history_old = StreamlitChatMessageHistory(key="chat_messages")

    return RunnableWithMessageHistory(
        chain,
        lambda session_id: DynamoDBChatMessageHistory(
            table_name=table_name, session_id=session_id
        ),
        input_messages_key="question",
        history_messages_key="history",
        output_messages_key="response",
    )


# Función para manejar errores de Bedrock, aqui se busca que se vuelve a repetir la consulta
def handle_error(error):
    st.error("Ocurrió un problema. Por favor, repite tu consulta.")
    st.write("Detalles técnicos (para depuración):")
    st.code(str(error))  # Mostrar los detalles del error para propósitos de depuración

###################################################################################################

def invoke_with_retriesnew(chain, prompt, history, config, max_retries=10):
    attempt = 0
    warning_placeholder = st.empty()  # Placeholder para mensajes de advertencia
    response_placeholder = st.empty()  # Placeholder para la respuesta del asistente
    run_id = None  # Inicializar el run_id

    while attempt < max_retries:
        try:
            print(f"Reintento {attempt + 1} de {max_retries}")  # Log en consola

            with response_placeholder.container():
                full_response = ''

                # Capturar el run_id solo del intento exitoso
                with collect_runs() as cb:
                    for chunk in chain.stream({"question": prompt, "history": history}, config):
                        if 'response' in chunk:
                            full_response += chunk['response']
                            response_placeholder.markdown(full_response)
                        else:
                            full_context = chunk['context']

                # Si la ejecución fue exitosa, obtener el run_id
                if cb.traced_runs:
                    run_id = cb.traced_runs[0].id

                # Guardar respuesta del asistente en el historial
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_response,
                    "run_id": run_id  # Guardamos el run_id correcto
                })

                warning_placeholder.empty()  # Limpiar el mensaje de espera
                return  # Salir exitosamente de la función

        except botocore.exceptions.BotoCoreError as e:
            attempt += 1
            if attempt == 1:
                warning_placeholder.markdown("⌛ Esperando generación de respuesta...")
            print(f"Error en reintento {attempt}: {str(e)}")
            if attempt == max_retries:
                warning_placeholder.markdown("⚠️ No fue posible generar la respuesta.  Por favor, vuelve a introducir tu pregunta.")

        except Exception as e:
            attempt += 1
            if attempt == 1:
                warning_placeholder.markdown("⌛ Esperando generación de respuesta...")
            print(f"Error inesperado en reintento {attempt}: {str(e)}")
            if attempt == max_retries:
                warning_placeholder.markdown("⚠️ No fue posible generar la respuesta.  Por favor, vuelve a introducir tu pregunta.")


feedback_option = "faces"  # Puede cambiarse a "thumbs" si se requiere


# Modificar la función main para usar la lógica de reintento
def main():

    ## Esto es para mostrar mensaje inicial, de lo que puede o no hacer el chatbot
    #if "messages" not in st.session_state:
    #    clear_chat_history()

    st.markdown(
    """
    <style>
        /* Ocultar el menú de los tres puntos */
        #MainMenu {
            visibility: hidden;
        }
        
        /* Ocultar el botón "Deploy" */
        .stAppDeployButton {
            visibility: hidden;
        }
    </style>
    """,
    unsafe_allow_html=True
)

    #### El session_id es lo que chat se le cargará al usuario
    query_params = st.query_params  # Para versiones recientes
    user_id =  query_params.get("user_id", "") #"langsmithfeedbackprueba@gmail.com"  #query_params.get("user_id", "")
    persona_id =  query_params.get("id_persona", "")#"101964"
    servidor = query_params.get("url_request","") #"C"  


    #st.write(user_id)
    if user_id:
        st.session_state.session_id =session_id = user_id  # Guardarlo en la sesión
        st.session_state.persona_id = persona_id  # Guardarlo en la sesión
        st.session_state.servidor = servidor

        st.success(f"Usuario: {st.session_state.session_id}")

        api_url = "https://compras135.ufm.edu/repositorio_procesos_api.php"

        if st.session_state.servidor == 'I':
            api_url = "https://intranet.ufm.edu/repositorio_procesos_api.php"


        # Parámetros para el POST (form-data)
        payload = {
            "centroCostosPermisos": "1",
            "id_persona": st.session_state.persona_id  # Se envía el ID de la persona desde la sesión
        }
         

        # Encabezados para la solicitud (form-data usa `x-www-form-urlencoded`)
        # Agregar más encabezados, importante, sino se tiene User-Agent da forbidden
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        # Hacer el POST automáticamente cuando hay un user_id
        with st.spinner("Obteniendo centros de costos..."):
            response = requests.post(api_url, data=payload, headers=headers)

  
        if response.status_code == 200:
            data = response.json()  # Convertir la respuesta en JSON

            # Guardar el JSON completo de los permisos en `st.session_state`
            st.session_state.centros_costos = data  

        else:
            st.error(f"⚠️ Acceso denegado: {response.status_code}")
            st.text(response.text)  # Mostrar el error en texto si lo hay
            st.stop()


    else:

        st.error("⚠️ Acceso denegado.")
        st.stop()  # Detiene la ejecución de Streamlit

    
    history = DynamoDBChatMessageHistory(table_name=table_name, session_id=session_id)

    
     
    if "centros_costos" in st.session_state and st.session_state.centros_costos:
        # Filtrar solo los centros que tienen "ACTIVO": "Y"
        centros_activos = [item["NOMBRE_MOSTRAR"] for item in st.session_state.centros_costos if item["ACTIVO"] == "Y"]

        centros_texto = "\n".join([f"- {nombre}" for nombre in centros_activos]) if centros_activos else "No tienes áreas disponibles."
    
    else:
        centros_texto = "No tienes áreas disponibles."
        st.stop()


    descripcion_chatbot = (
    "\n"
    "Soy tu asistente sobre procesos de la UFM, ¿En qué puedo apoyarte?\n"
    "- Responder consultas sobre procesos específicos, guiándote paso a paso.\n"
    "- Mostrarte una lista de procesos relacionados y ayudarte a encontrar el proceso adecuado.\n"
    "- Proporcionarte enlaces directos a documentos y flujogramas relevantes.\n"
    "- Aclarar dudas y solicitar más detalles para asegurar que obtengas la mejor respuesta posible.\n"
    "- Ofrecer información sobre tiempos estimados, participantes y aspectos clave de cada paso de un proceso.\n\n"
    "Mi misión es facilitarte el acceso a la información y guiarte a través de los procesos de la manera más eficiente posible.\n\n"
    "---\n"
)  
    
    st.write(descripcion_chatbot)
    st.warning(f"Puedes consultar procesos de las siguientes áreas:\n{centros_texto}")




    # Cargar mensajes de Dynamo DB y llenar el history
    if "messages" not in st.session_state:
        #clear_chat_history()

        st.session_state.messages = []
    
        # Cargar los mensajes guardados de dynamo DB
        stored_messages = history.messages  # Retrieve all stored messages
    
        # Llenar el estado de la sesion con los mensajes obtenidos, importante que se utilizan el rol user / assistant
        for msg in stored_messages:
            role = "user" if msg.__class__.__name__ == "HumanMessage" else "assistant"
            st.session_state.messages.append({"role": role, "content": msg.content})


    retriever = AmazonKnowledgeBasesRetriever(
    knowledge_base_id= "OWLYEEHPY5", ##Antiguo: "I9HQYMMI4A",
    retrieval_config=generar_configuracion_retriever_new()
    )




    SYSTEM_PROMPT = (f"""
                     
## Base de conocimientos (solo puedes responder con esta información):

{{context}}

- Debes **responder estrictamente con la información contenida en el contexto recuperado (`context`)**.
- **NO generes información que no esté explícitamente en `context`**.
- **NO inventes procesos, códigos, ni nombres de procesos**. Si un usuario pregunta sobre un proceso que **no está en el contexto, responde que no hay información disponible o no tiene permisos para acceder a esta información**.
- Si `context` está vacío o no contiene procesos relevantes, responde:  
  **"No se encontró información relevante sobre este proceso en la documentación proporcionada o no tienes permisos para acceder a esta información"**
                     

## Instrucciones:

**Rol**: 
Adquiere el rol de un informador con conocimientos de metodología de procesos y con gran oratoria para poder explicarlos de manera sencilla y clara. Estos procesos corresponden a la Universidad Francisco Marroquín de Guatemala, Panamá y Madrid. Quiero que hagas preguntas al usuario para que mejore la forma en la que te solicita la información y no te centres en responder inmediatamente, si hay información que pueda estar en varias partes de la documentación que te hemos agregado. No vas a buscar la información a internet, esto desvirtuaría los procesos que hemos creado.

**Publico**: 
El publico objetivo es personal de la universidad, catedráticos, profesores, personal administrativo de los departamentos y unidades académicas y cualquier otra persona de carácter administrativo u otras áreas. Es probable que no te den mucho detalle en su consulta, así que por favor centra la pregunta del usuario añadiéndole nuevas preguntas para mejorar el conocimiento de que quieren conseguir.

Siempre que recibas una consulta, debes hacer **preguntas de aclaración** solicitando más contexto y proporcionando una lista de los posibles procesos relacionados con la consulta, **ordenados por prioridad de mayor a menor relación con el proceso (score), es decir que pueda encajar con un grado entre 0 y 1 de correlación con la temática preguntada**. Usa la aproximación para ello. La estructura de la respuesta inicial será la siguiente:

1. **Preguntas de aclaración:** Haz preguntas (por ejemplo si sabe el departamento al que pertenece el proceso, o preguntar al usuario que de más detalles sobre lo qué quiere realizar ) para pedir más detalles o confirmar el proceso específico que el usuario desea obtener. 

2. **Lista de procesos relacionados:** Muestra una lista de procesos relacionados con la consulta **únicamente** si están presentes en el `context`. 
- **Solo menciona procesos que aparecen exactamente en `context`.**
- **NO debes generar procesos que no se encuentren en `context`.**
- **NO inventes códigos de procesos ni hagas suposiciones sobre su existencia.**
- **NO asumas que existen otros procesos si no están explícitamente en `context`.**
- **Si el usuario pregunta por un proceso que no está en `context`, responde directamente que no tienes información y que el usuario no tiene permisos para acceder a esta información. NO intentes sugerir procesos similares de otras áreas.**
- **Si el `context` no contiene procesos relacionados con la consulta del usuario, responde:**
  **"No se encontraron procesos relacionados con tu consulta en la documentación proporcionada o no tienes permisos para acceder a esta información"**
- La lista debe estar **ordenada por prioridad** de mayor a menor, basándote en la relevancia de los procesos dentro del `context`.
- Usa el siguiente formato para cada proceso encontrado en `context`:
   - **Nombre del proceso (código del proceso)**
   - Repite este formato para cada proceso relevante.

3. **Espera confirmación:** (Mostrar un mensaje al usuario para que elija uno de los procesos mostrados, solicitarle que escriba el código o nombre del proceso, además mencionar que si el proceso que busca no se encuentra puede ampliarse el listado de procesos relacionados)
   - Una vez que el usuario confirme qué proceso le interesa, procede a entregar la información detallada siguiendo los pasos descritos en la sección "Pasos Obligatorios" que aparece más abajo.

4. **Si el usuario quiere cambiar de tema, pregúntale si ha terminado con la consulta anterior, y así vuelve a repetir estos pasos tantas veces como el usuario necesite.**

## Pasos Obligatorios (Una vez confirmada la selección):
Cuando el usuario confirme el proceso que desea conocer, sigue estrictamente los siguientes pasos (formatea la respuesta de manera clara y organizada):

1. **Identificación del proceso:** Busca el proceso que te ha pedido el usuario y devuelve la información en formato tabla de la siguiente manera:
   - **Primera Columna:** Código del proceso mencionado.
   - **Segunda Columna:** Nombre del proceso mencionado.
   - **Tercera Columna:** Link al documento de pasos: Con un *hipervínculo* que diga **Ver documento de pasos** y el link-documento-pasos incrustado al mismo.
   - **Cuarta Columna:** Link al Flujograma : Con la misma estructura que el anterior con el link-flujograma, el *hipervínculo* con un texto que diga **Ver Flujograma**.

2. **Explicación detallada:** Proporciona una explicación lo más detallada posible, que incluya:
   - **Objetivo del proceso.** [Descripción del objetivo o propósito del proceso].
   - **Pasos del proceso:** Asegúrate de identificar **todos los pasos** desde el inicio hasta el final del proceso (por ejemplo, del paso 1 al paso 11).
        
     **Instrucciones para asegurar que no se omita ningún paso:** 
        - **Verifica que todos los pasos consecutivos estén presentes**, desde el primero hasta el último (por ejemplo, si el proceso tiene 11 pasos, asegúrate de que todos los pasos del 1 al 11 estén incluidos).
        - **Recorre todo el contenido disponible** y **combina la información fragmentada** si un paso está dividido en varias partes o aparece en diferentes secciones.
        - **No detengas la búsqueda hasta que identifiques todos los pasos declarados en la numeración completa.** Si los pasos están desordenados o fragmentados, organiza y presenta los pasos de manera secuencial (1, 2, 3,... 11).

        **Presenta cada paso siguiendo el formato a continuación:**
        - 1. [Nombre del paso]:
            - **Descripción:** Explica el paso en detalle.
            - **Tiempos:** [Tiempo estimado para completar el paso].
            - **No negociables:** [Cosas que no se pueden omitir o cambiar].
            - **Participantes:** [Personas o áreas involucradas].
        - 2. [Nombre del paso]:
           - **Descripción:** Explica el paso en detalle.
           - **Tiempos:** [Tiempo estimado para completar el paso].
           - **No negociables:** [Cosas que no se pueden omitir o cambiar].
           - **Participantes:** [Personas o áreas involucradas].

        - Repite este formato para cada paso. Asegúrate de incluir todos los fragmentos relacionados con el proceso y de que cada subelemento (como tiempos, no negociables, participantes) esté separado con saltos de línea (`\n`) para mantener la estructura clara y organizada.
        
        
    - **Confirma con el usuario si pudo resolver su consulta**.


## Reglas para Fragmentos de Información:
- Si el proceso está dividido en varios fragmentos o "chunks", debes combinar toda la información relacionada con el código del proceso antes de generar la respuesta.
- Usa el **código del proceso** para identificar y concatenar todos los fragmentos que pertenezcan al mismo proceso, proporcionando una explicación completa sin omitir ningún paso, tiempo, no negociable o participante, incluso si están en diferentes *chunks* o fragmentos.

## Listado Completo por Unidad ##
Si el usuario solicita ver un listado completo de los procesos de una unidad, responde con el siguiente formato:

1. **Listado Completo de Procesos:**
   - Presenta todos los procesos disponibles en `context` de la unidad solicitada.
   - Utiliza el siguiente formato para cada proceso: (Repite este formato para cada proceso):
       1. Nombre del proceso (Código del proceso)
       
       **Ejemplo:**
        1. UFM-CODIGOAREA-001 - Proceso A
        2. UFM-CODIGOAREA-002 - Proceso B 
        3. UFM-CODIGOAREA-003 - Proceso C 

   **Nota:** Si no se encuentran procesos para la unidad solicitada, responde: 'No se encontraron procesos para la unidad o no se tiene permiso para acceder a esta información'

## Manejo de Consultas sin Información Relevante:
- **Si el usuario pregunta por un proceso que no está en `context`, responde sin inventar información.**
- **NO generes respuestas basadas en conocimiento previo o inferencias si la información no está en `context`.**
- **Si `context` está vacío o no contiene procesos relevantes para la consulta del usuario, responde con:**
  **"No se encontró información relevante sobre este proceso en la documentación proporcionada o no tienes permisos para acceder a esta información."**
- **NO intentes reformular la consulta ni sugerir procesos fuera del contexto recuperado.**

## Manejo de Respuestas Cortas 
- Si la consulta solo requiere un enlace o un dato específico (nombre o código de proceso), proporciona únicamente esa información sin desglosar todos los pasos.

    """
    )


    chain_with_history = create_chain_with_history(retriever,SYSTEM_PROMPT)


    # Mostrar historial de conversación
    for i, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.write(message["content"])

            # Mostrar feedback solo para respuestas del asistente
            if message["role"] == "assistant" and "run_id" in message and message["run_id"]:
                feedback_result = streamlit_feedback(
                    feedback_type=feedback_option,
                    optional_text_label="[Opcional] Comentarios adicionales",
                    key=f"feedback_{message['run_id']}",
                )

                # Guardar feedback en session_state y LangSmith
                if feedback_result and "score" in feedback_result:
                    message["feedback"] = feedback_result["score"]

                    # Mapeo de puntuaciones
                    score_mappings = {
                        "thumbs": {"👍": 1, "👎": 0},
                        "faces": {"😀": 1, "🙂": 0.75, "😐": 0.5, "🙁": 0.25, "😞": 0},
                    }
                    score = score_mappings[feedback_option].get(feedback_result["score"])

                    if score is not None:
                        try:
                            feedback_type_str = f"{feedback_option} {feedback_result['score']}"
                            feedback_record = client.create_feedback(
                                message["run_id"],
                                feedback_type_str,
                                score=score,
                                comment=feedback_result.get("text"),
                            )
                            message["feedback_id"] = str(feedback_record.id)
                            st.success("✅ Feedback registrado correctamente.")
                        except Exception as e:
                            st.error(f"❌ Error al enviar feedback: {e}")

    # Capturar input del usuario
    if prompt := st.chat_input("Escribe tu mensaje aquí..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        config = {"configurable": {"session_id": session_id}}

        # Capturar el run_id con collect_runs()
        #with collect_runs() as cb:
        invoke_with_retriesnew(chain_with_history, prompt, st.session_state.messages, config)
########
            # Guardar el run_id generado en la respuesta del asistente
       #     if cb.traced_runs:
       #         run_id = cb.traced_runs[0].id
       #     else:
       #         run_id = None

        # Obtener la última respuesta del asistente y añadir el run_id
       # if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
       #     st.session_state.messages[-1]["run_id"] = run_id




if __name__ == "__main__":
    main()




