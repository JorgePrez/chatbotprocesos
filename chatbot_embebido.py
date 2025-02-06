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

#from langchain_openai.chat_models import ChatOpenAI

from collections import defaultdict
from langchain.schema import Document  # Asegúrate de importar Document si es necesario
from dotenv import load_dotenv


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



SYSTEM_PROMPT_JOIN_2 = (
"""

## Base de conocimientos:

{context}

## Instrucciones:

**Rol**: 
Adquiere el rol de un informador con conocimientos de metodología de procesos y con gran oratoria para poder explicarlos de manera sencilla y clara. Estos procesos corresponden a la Universidad Francisco Marroquín de Guatemala, Panamá y Madrid. Quiero que hagas preguntas al usuario para que mejore la forma en la que te solicita la información y no te centres en responder inmediatamente, si hay información que pueda estar en varias partes de la documentación que te hemos agregado. No vas a buscar la información a internet, esto desvirtuaría los procesos que hemos creado.

**Publico**: 
El publico objetivo es personal de la universidad, catedráticos, profesores, personal administrativo de los departamentos y unidades académicas y cualquier otra persona de carácter administrativo u otras áreas. Es probable que no te den mucho detalle en su consulta, así que por favor centra la pregunta del usuario añadiéndole nuevas preguntas para mejorar el conocimiento de que quieren conseguir.

Siempre que recibas una consulta, debes hacer **preguntas de aclaración** solicitando más contexto y proporcionando una lista de los posibles procesos relacionados con la consulta, **ordenados por prioridad de mayor a menor relación con el proceso (score), es decir que pueda encajar con un grado entre 0 y 1 de correlación con la temática preguntada**. Usa la aproximación para ello. La estructura de la respuesta inicial será la siguiente:

1. **Preguntas de aclaración:** Haz preguntas (por ejemplo si sabe el departamento al que pertenece el proceso, o preguntar al usurio que de más detalle sobree lo qué quiere realizar ) para pedir más detalles o confirmar el proceso específico que el usuario desea obtener. 

2. **Lista de procesos relacionados:** Muestra una lista de procesos relacionados con la consulta. La lista debe estar **ordenada por prioridad** de mayor a menor, basándote en la relevancia de los procesos para la consulta recibida. Usa el siguiente formato:
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
   - Presenta todos los procesos disponibles en la unidad solicitada.
   - Utiliza el siguiente formato para cada proceso: (Repite este formato para cada proceso):
       1. Nombre del proceso (Código del proceso)
       
       **Ejemplo:**
        1. UFM-IT-001 - Proceso A
        2. UFM-IT-002 - Proceso B 
        3. UFM-IT-003 - Proceso C 

   **Nota:** Si no se encuentran procesos para la unidad solicitada, responde: 'No se encontraron procesos para la unidad'

## Manejo de Consultas sin Información Relevante
- Si no hay procesos disponibles en el contexto (base de conocimientos) que coincidan con la consulta, responde de manera clara explicando que no existe información disponible:
  'Lo siento, no se encontró información relevante para tu consulta en el contexto proporcionado.'

## Manejo de Respuestas Cortas 
- Si la consulta solo requiere un enlace o un dato específico (nombre o código de proceso), proporciona únicamente esa información sin desglosar todos los pasos.

"""
)


# Initialize the DynamoDB chat message history
###historyDynamoDb = DynamoDBChatMessageHistory(
#    table_name="SessionTable", 
#    session_id="user123"
#)


# Función para crear el prompt dinámico
def create_prompt_template():
    return ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT_JOIN_2),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{question}")
        ]
    )


areas_codigos = [
    {"codigo": "ADM", "nombre": "Admisiones", "activo": True},
    {"codigo": "AES", "nombre": "Atención al estudiante", "activo": True},
    {"codigo": "CETA", "nombre": "CETA", "activo": True},
    {"codigo": "CSM", "nombre": "Clínicas Salud", "activo": True},
    {"codigo": "COLAB", "nombre": "CoLab", "activo": True},
    {"codigo": "CON", "nombre": "Contabilidad", "activo": True},
    {"codigo": "CE", "nombre": "Crédito Educativo", "activo": True},
    {"codigo": "CTAC", "nombre": "Cuenta Corriente", "activo": True},
    {"codigo": "IT", "nombre": "Tecnología", "activo": True},
    {"codigo": "MERC", "nombre": "Mercadeo", "activo": True},
    {"codigo": "PU", "nombre": "Publicaciones", "activo": True},
    {"codigo": "REG", "nombre": "Registro", "activo": True},
    {"codigo": "RH", "nombre": "Recursos Humanos", "activo": True},
    {"codigo": "TES", "nombre": "Tesorería", "activo": True},
    {"codigo": "UFM-LABS", "nombre": "UFM LABS", "activo": True},
]

# Construimos el mensaje con el listado de áreas activas
mensaje_areas = "\nÁreas disponibles:\n"
for area in areas_codigos:
    if area["activo"]:
        mensaje_areas += f"- **{area['nombre']}** ({area['codigo']})\n"


# Función que genera la configuración completa del retriever
def generar_configuracion_retriever():
    # Obtener los códigos de áreas inactivas
    inactivas = [area["codigo"] for area in areas_codigos if not area["activo"]]

    # Construir la configuración base
    config = {
        "vectorSearchConfiguration": {
            "numberOfResults":  100  #maximo 100
        }
    }

    # Si hay áreas inactivas, agregar el filtro
    if inactivas:
        config["vectorSearchConfiguration"]["filter"] = {
            "notIn": {
                "key": "codigo_area",
                "value": inactivas
            }
        }

    return config

# Crear el retriever con la configuración generada
retriever = AmazonKnowledgeBasesRetriever(
    knowledge_base_id="I9HQYMMI4A",
    retrieval_config=generar_configuracion_retriever()
)



#################################################################################################

# Función para recuperar y depurar el contexto

def obtener_contexto(inputs):
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



# Crear el pipeline con depuración
context_pipeline = RunnableLambda(obtener_contexto)



table_name = "SessionTable"


# Chain con historial de mensajes
def create_chain_with_history():
    prompt = create_prompt_template()

    chain = (
        RunnableParallel({
            "context": context_pipeline,
            "question": itemgetter("question"),
            "history": itemgetter("history"),
        })
        .assign(response=prompt | llmClaude   | StrOutputParser())
        .pick(["response", "context"])
    )

    #print(chain)

    history_old = StreamlitChatMessageHistory(key="chat_messages")

    ##lambda session_id: 
    return RunnableWithMessageHistory(
        chain,
        lambda session_id: DynamoDBChatMessageHistory(
        table_name=table_name, session_id=session_id
    ),
        input_messages_key="question",
        history_messages_key="history",
        output_messages_key="response",
    )



#{mensaje_areas} 

descripcion_chatbot = (
    "Hola , soy tu asistente sobre procesos de la UFM. ¿En que puedo ayudarte?\n"
    "- Responder consultas sobre procesos específicos, guiándote paso a paso.\n"
    "- Mostrarte una lista de procesos relacionados y ayudarte a encontrar el proceso adecuado.\n"
    "- Proporcionarte enlaces directos a documentos y flujogramas relevantes.\n"
    "- Aclarar dudas y solicitar más detalles para asegurar que obtengas la mejor respuesta posible.\n"
    "- Ofrecer información sobre tiempos estimados, participantes y aspectos clave de cada paso de un proceso.\n\n"
    "Mi misión es facilitarte el acceso a la información y guiarte a través de los procesos de la manera más eficiente posible."
)

# Función para limpiar historial de chat
#def clear_chat_history():
    #st.session_state.messages = [{"role": "assistant", "content": f"Soy tu asistente sobre procesos de la UFM,{descripcion_chatbot }"}]


# Función para manejar errores de Bedrock, aqui se busca que se vuelve a repetir la consulta
def handle_error(error):
    st.error("Ocurrió un problema. Por favor, repite tu consulta.")
    st.write("Detalles técnicos (para depuración):")
    st.code(str(error))  # Mostrar los detalles del error para propósitos de depuración

###################################################################################################


# Función para manejar errores de Bedrock y reintentar la llamada
def invoke_with_retries6(chain, prompt, history, config, max_retries=10):
    attempt = 0
    warning_placeholder = st.empty()  # Marcador de posición para mostrar un solo mensaje de advertencia

    # Contenedor para la respuesta del asistente
    response_placeholder = st.empty()
    
    while attempt < max_retries:
        try:
            # Imprimir en la consola el mensaje de reintento
            print(f"Reintento {attempt + 1} de {max_retries}")

            with response_placeholder.container():  # Usar el mismo contenedor para la respuesta del asistente
                full_response = ''
                for chunk in chain.stream({"question": prompt, "history": history}, config):
                    if 'response' in chunk:
                        full_response += chunk['response']
                        response_placeholder.markdown(full_response)
                    else:
                        full_context = chunk['context']
                response_placeholder.markdown(full_response)

                st.session_state.messages.append({"role": "assistant", "content": full_response})
                warning_placeholder.empty()  # Limpiar el mensaje de espera cuando termine exitosamente
                return  # Si la llamada es exitosa, salir de la función

        except botocore.exceptions.BotoCoreError as e:
            attempt += 1

            if attempt == 1:  # Solo mostrar la primera vez que se hace un reintento
                warning_placeholder.markdown(
                    "⌛ Esperando generación de respuesta...",
                    unsafe_allow_html=True
                )
            
            print(f"Error en reintento {attempt} de {max_retries}: {str(e)}")  # Imprimir en consola
            if attempt == max_retries:
                warning_placeholder.markdown(
                    "⚠️ **No fue posible generar la respuesta, vuelve a ingresar tu consulta.**",
                    unsafe_allow_html=True
                )
        except Exception as e:
            attempt += 1

            if attempt == 1:  # Solo mostrar la primera vez que se hace un reintento
                warning_placeholder.markdown(
                    "⌛ Esperando generación de respuesta...",
                    unsafe_allow_html=True
                )
            print(f"Error inesperado en reintento {attempt} de {max_retries}: {str(e)}")  # Imprimir en consola
            if attempt == max_retries:
                warning_placeholder.markdown(
                    "⚠️ **No fue posible generar la respuesta, vuelve a ingresar tu consulta.**",
                    unsafe_allow_html=True
                )


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

    #query_params = st.experimental_get_query_params()  # Para versiones anteriores
    #user_id = query_params.get("user_id", [""])[0]  # Extraer el usuario
    query_params = st.query_params  # Para versiones recientes
    user_id = query_params.get("user_id", "")

    #st.write(user_id)
    if user_id:
        st.session_state.session_id =session_id = user_id  # Guardarlo en la sesión
        #st.write(f"Bienvenido, usuario: {user_id}")
        st.success(f"Usuario: {st.session_state.session_id}")
        #st.sidebar.success(f"Usuario: {st.session_state.username}")


    else:
       # st.write("Sin identificador de usuario.")   
        #st.error("⚠️ No se proporcionó un identificador de usuario. Acceso denegado.")
        st.error("⚠️ Acceso denegado.")
        st.stop()  # Detiene la ejecución de Streamlit

    #session_id = "pruebascompras@gmail.com" #st.session_state.username 

    #session_id = "user123"  # Importante se necesita que cada usuario tenga un identificador único, sería útil colocar algún identificador
    history = DynamoDBChatMessageHistory(table_name=table_name, session_id=session_id)

    
    descripcion_chatbot = (
    "\n"
    "Soy tu asistente sobre procesos de la UFM, ¿En qué puedo apoyarte?\n"
    "- Responder consultas sobre procesos específicos, guiándote paso a paso.\n"
    "- Mostrarte una lista de procesos relacionados y ayudarte a encontrar el proceso adecuado.\n"
    "- Proporcionarte enlaces directos a documentos y flujogramas relevantes.\n"
    "- Aclarar dudas y solicitar más detalles para asegurar que obtengas la mejor respuesta posible.\n"
    "- Ofrecer información sobre tiempos estimados, participantes y aspectos clave de cada paso de un proceso.\n\n"
    "Mi misión es facilitarte el acceso a la información y guiarte a través de los procesos de la manera más eficiente posible."
)  
    st.write(descripcion_chatbot)


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

    streaming_on = True

    # Botón para eliminar contenido de la pantalla
   # st.sidebar.button('Limpiar pantalla', on_click=clear_chat_history)
    ## deberia eliminar historial

   # st.sidebar.button("Logout", on_click=st.session_state.clear())
       # st.session_state.clear()  # Limpia todas las variables de sesión
           # st.experimental_rerun()  # Reinicia la aplicación para reflejar cambios
    

   ## st.divider()


    chain_with_history = create_chain_with_history()

    ##st.write(SYSTEM_PROMPT_JOIN)

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    if prompt := st.chat_input("Escribe tu mensaje aquí..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        config = {"configurable": {"session_id": session_id}}  


        if streaming_on:
            invoke_with_retries6(chain_with_history, prompt, st.session_state.messages, config)




if __name__ == "__main__":
    main()




