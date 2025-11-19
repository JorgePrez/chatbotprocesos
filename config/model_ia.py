from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableParallel
from langchain_core.output_parsers import StrOutputParser
from langchain_aws import AmazonKnowledgeBasesRetriever, ChatBedrock
from operator import itemgetter
import boto3
from langchain_aws import ChatBedrock
from typing import List, Dict
from pydantic import BaseModel
import boto3
from botocore.exceptions import NoCredentialsError

import botocore
#from langchain.callbacks.tracers.run_collector import collect_runs



IS_TESTING = False  # Cambiar a False para producción


# ✅ Importar solo en producción
if not IS_TESTING:
    from langchain.callbacks import collect_runs

session = boto3.Session(profile_name="testing" if IS_TESTING else None)


bedrock_runtime = boto3.client(
        service_name="bedrock-runtime",
        region_name="us-east-1",
    )

model_kwargs = {
    "max_tokens": 4096,
    "temperature": 0.0,
    "top_k": 250,
    "top_p": 1,
    "stop_sequences": ["\n\nHuman"],
}

# ✅ IDs de modelos según entorno
if IS_TESTING:
    model_id_3_7 = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    model_id_3_5 = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
else:
    model_id_3_7 = "arn:aws:bedrock:us-east-1:552102268375:application-inference-profile/hkqiiam51emk"
    model_id_3_5 = "arn:aws:bedrock:us-east-1:552102268375:application-inference-profile/yg7ijraub0q5"



# ✅ Modelo Claude 3.7 Sonnet (para la chain principal)
model = ChatBedrock(
    client=bedrock_runtime,
    model_id=model_id_3_7,
    model_kwargs=model_kwargs,
    provider="anthropic"
)

# ✅ Modelo Claude 3.5 Sonnet (para renombrar)
modelNames = ChatBedrock(
    client=bedrock_runtime,
    model_id=model_id_3_5,
    model_kwargs=model_kwargs,
    provider="anthropic"
)


#inference_profile3_5claudehaiku="us.anthropic.claude-3-5-haiku-20241022-v1:0"
#inference_profile3claudehaiku="us.anthropic.claude-3-haiku-20240307-v1:0"
#inference_profile3_5Sonnet="us.anthropic.claude-3-5-sonnet-20240620-v1:0"
#inference_profile3_7Sonnet="us.anthropic.claude-3-7-sonnet-20250219-v1:0"


#inference_profile3_7Sonnet="arn:aws:bedrock:us-east-1:552102268375:application-inference-profile/tcsgx7nj4mf1"





###########################################
SYSTEM_PROMPT_PROCESOS = (f"""
                     
## Base de conocimientos (solo puedes responder con esta información):

{{context}}

- Debes **responder estrictamente con la información contenida en el contexto recuperado (`context`)**.
- **NO generes información que no esté explícitamente en `context`**.
- **NO inventes procesos, códigos, ni nombres de procesos**. Si un usuario pregunta sobre un proceso que **no está en el contexto, responde que no hay información disponible o no tiene permisos para acceder a esta información**.
- Si `context` está vacío o no contiene procesos relevantes, responde:  
  **"No se encontró información relevante sobre este proceso en la documentación proporcionada o no tienes permisos para acceder a esta información"**
                     

## Instrucciones:

Importante sobre el formato:
No utilices encabezados Markdown como `#`, `##`, `###`, ni títulos grandes. Todo el texto debe tener el mismo tamaño. Puedes usar listas numeradas o viñetas y aplicar negritas simples si es necesario, pero sin cambiar el tamaño del texto ni generar encabezados destacados.

**Rol**: 
Adquiere el rol de un informador con conocimientos de metodología de procesos y con gran oratoria para poder explicarlos de manera sencilla y clara. Estos procesos corresponden a la Universidad Francisco Marroquín de Guatemala, Panamá y Madrid. Quiero que hagas preguntas al usuario para que mejore la forma en la que te solicita la información y no te centres en responder inmediatamente, si hay información que pueda estar en varias partes de la documentación que te hemos agregado. No vas a buscar la información a internet, esto desvirtuaría los procesos que hemos creado.

**Publico**: 
El publico objetivo es personal de la universidad, catedráticos, profesores, personal administrativo de los departamentos y unidades académicas y cualquier otra persona de carácter administrativo u otras áreas. Es probable que no te den mucho detalle en su consulta, así que por favor centra la pregunta del usuario añadiéndole nuevas preguntas para mejorar el conocimiento de que quieren conseguir.

Siempre que recibas una consulta, debes hacer **preguntas de aclaración** solicitando más contexto y proporcionando una lista de los posibles procesos relacionados con la consulta, **ordenados por prioridad de mayor a menor relación con el proceso (score), es decir que pueda encajar con un grado entre 0 y 1 de correlación con la temática preguntada**. Usa la aproximación para ello. La estructura de la respuesta inicial será la siguiente:
                          
Si el `context` contiene un listado completo de procesos relacionados con una unidad específica solicitada por el usuario (por ejemplo: "listado completo de procesos de IT"), muestra directamente ese listado usando el formato de la sección **Listado Completo por Unidad**, sin hacer preguntas de aclaración. No repitas la lista parcial ni ordenada por relevancia si ya tienes el listado completo en el contexto.

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

3. **Esperando confirmación:** (Mostrar un mensaje al usuario para que elija uno de los procesos mostrados, solicitarle que escriba el código o nombre del proceso, además mencionar que si el proceso que busca no se encuentra puede ampliarse el listado de procesos relacionados)
   - Una vez que el usuario confirme qué proceso le interesa, procede a entregar la información detallada siguiendo los pasos descritos en la sección "Pasos Obligatorios" que aparece más abajo.

4. **Si el usuario quiere cambiar de tema, pregúntale si ha terminado con la consulta anterior, y así vuelve a repetir estos pasos tantas veces como el usuario necesite.**

## Pasos Obligatorios (Una vez confirmada la selección):
Cuando el usuario confirme el proceso que desea conocer, sigue estrictamente los siguientes pasos (formatea la respuesta de manera clara y organizada):

1. **Identificación del proceso:** Busca el proceso que te ha pedido el usuario y devuelve la información en formato tabla de la siguiente manera:
   - **Primera Columna:** Código del proceso mencionado.
   - **Segunda Columna:** Nombre del proceso mencionado.
   - **Tercera Columna:** Link al Documento escrito: Con un *hipervínculo* que diga **Ver documento escrito** y el link-documento-pasos incrustado al mismo.
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
   - Debes iniciar el bloque de listado con una línea descriptiva simple en **negrita**, por ejemplo: **Listado completo de procesos de IT:** ,  No utilices títulos visuales destacados como encabezados Markdown (`#`, `##`, etc.).
   - Presenta todos los procesos disponibles en `context` de la unidad solicitada.
   - Utiliza el siguiente formato para cada proceso: (Repite este formato para cada proceso):
       1. Nombre del proceso (Código del proceso)
       
       **Ejemplo:**
        1. UFM-CODIGOAREA-001 - Proceso A
        2. UFM-CODIGOAREA-002 - Proceso B 
        3. UFM-CODIGOAREA-003 - Proceso C 

   **Nota:** Si no se encuentran procesos para la unidad solicitada, responde: 'No se encontraron procesos para la unidad o no se tiene permiso para acceder a esta información'

2. **Preguntas posteriores al listado completo:**
   - Después de mostrar el listado completo, agrega automáticamente un breve bloque de seguimiento con preguntas como:
                          
     - ¿Hay algún proceso de esta lista que te interese conocer en detalle?
     - ¿Deseas que te explique alguno de estos procesos paso a paso?
     - Si te interesa alguno, por favor indícame su **nombre** o **código de proceso** para que pueda mostrarte los detalles.

   - Estas preguntas deben mantener un tono empático, claro y útil, fomentando que el usuario continúe la conversación sin sentirse bloqueado.
                          
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


def create_prompt_template_procesos():
    return ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT_PROCESOS),
            MessagesPlaceholder(variable_name="historial"),
            ("human", "{question}")
        ]
    )


def limpiar_metadata_retrieved(docs):
    for doc in docs:
        # 1. Limpiar metadata directa
        #,"score"
        for clave in ["x-amz-bedrock-kb-data-source-id", "x-amz-bedrock-kb-source-uri", "location", "type", "score"]:
            doc.metadata.pop(clave, None)

        # 2. Limpiar metadata anidada dentro de source_metadata
        if "source_metadata" in doc.metadata:
            for clave in ["x-amz-bedrock-kb-data-source-id", "x-amz-bedrock-kb-source-uri",  "codigo_area"]:
                doc.metadata["source_metadata"].pop(clave, None)
    return docs

# Base de conocimiento en Bedrock
BASE_CONOCIMIENTOS_PROCESOS = "JQW2MHWKBF" #"OBWA2AMNUJ" #JQW2MHWKBF


def generar_configuracion_retriever(codigos_activos: list) -> dict:
    config = {
        "vectorSearchConfiguration": {
            "numberOfResults": 100,
                  "rerankingConfiguration": {
                "bedrockRerankingConfiguration": {
                    "modelConfiguration": {
                        "modelArn": "arn:aws:bedrock:us-west-2::foundation-model/cohere.rerank-v3-5:0",
                    },
                    "numberOfRerankedResults": 20,
                    "metadataConfiguration": {
                    "selectionMode": "SELECTIVE",
                    "selectiveModeConfiguration": {
                            "fieldsToInclude": [
                                    {"fieldName": "identificador_proceso"},
                                    {"fieldName": "nombre_proceso"},
                                    {"fieldName": "area"},

                            ]
                        }
                    }
                },
                "type": "BEDROCK_RERANKING_MODEL"
            }
        }
    }

    if codigos_activos:
        config["vectorSearchConfiguration"]["filter"] = {
            "in": {
                "key": "codigo_area",
                "value": codigos_activos
            }
        }

    return config

from langchain.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda




REFORMULATE_WITH_HISTORY_PROMPT = PromptTemplate.from_template("""
Actúa como un reformulador de preguntas para un asistente especializado en procesos administrativos de la UFM.

Tu tarea es transformar la última pregunta del usuario en una versión clara, autosuficiente y específica, adecuada para buscar en una base de conocimientos estructurada por procesos, cada uno con un código como "UFM-ADM-009" y un nombre como "Visitas de colegios a UFM".
                                                               
Toma en cuenta el historial completo del chat:
- Si el usuario Responde con “Sí”, “Ajá” o “Correcto” luego de una sugerencia, reformula incluyendo el código y nombre del proceso sugerido.
- Si el usuario hace referencia a la posición de un ítem en una lista (ej: “el tercero”, “el último”, “ese”), identifica de qué proceso se trata y usa su nombre y código.
- Si el usuario da una palabra ambigua como “compras” , convierte eso en una consulta completa (ej: “Estoy buscando un proceso relacionado con compras...”).
- Si la pregunta o el input del usuario es lo suficientemente clara, simplemente repítela tal como está.
                                                               

Reglas adicionales:
- No inventes nombres ni códigos de procesos. Solo incluye nombres o códigos si ya han sido mencionados anteriormente en la conversación.
- Si el usuario pide un “listado” de procesos (por ejemplo: “dame un listado de IT” o “quiero ver procesos de admisiones”), reformula indicando explícitamente que desea **el listado completo** de procesos relacionados con la  unidad mencionada.
- Reformula de modo que la pregunta esté alineada con el formato de los procesos (nombre y código, si están disponibles).

Responde solo con la pregunta o input reformulado, sin ninguna explicación.

Historial del chat:
{history}

Última pregunta o input del usuario:
{question}

Pregunta o input reformulado:
""")

# Cadena de reformulación (usa el mismo modelo principal)
reformulate_chain = REFORMULATE_WITH_HISTORY_PROMPT | model | StrOutputParser()



def build_procesos_chain(codigos_activos: list):
    retriever = AmazonKnowledgeBasesRetriever(
        region_name="us-west-2",
        knowledge_base_id=BASE_CONOCIMIENTOS_PROCESOS,
        retrieval_config=generar_configuracion_retriever(codigos_activos)
    )

    filtered_retriever = retriever | RunnableLambda(limpiar_metadata_retrieved)


    prompt_template = create_prompt_template_procesos()

    chain = (
        RunnableParallel({
            "context": itemgetter("question") | filtered_retriever,
            "question": itemgetter("question"),
            "historial": itemgetter("historial"),
        })
        .assign(response=prompt_template | model | StrOutputParser())
        .pick(["response", "context"])
    )

    return chain

def run_procesos_chain(question, history, codigos_activos):
    ##print(codigos_activos) Centros de costos activos para debuggear
    chain = build_procesos_chain(codigos_activos)

    
    reformulated_question = reformulate_chain.invoke({
    "question": question,
    "history": history  
    })


##    print("\n==============================")
##    print("🔹 Pregunta original del usuario:")
##   print(question)
##    print("------------------------------")
##    print("🔄 Pregunta reformulada por el sistema:")
##    print(reformulated_question)
##    print("==============================\n")


    inputs = {
        "question": reformulated_question,
        "historial": history
    }
    return chain.stream(inputs)


#inference_profile3_5Sonnet="arn:aws:bedrock:us-east-1:552102268375:application-inference-profile/sc2jrj3crjn0"


#modelNames = ChatBedrock(
#    client=bedrock_runtime,
#    model_id=inference_profile3_5Sonnet,
#    model_kwargs=model_kwargs,
#    provider="anthropic"  
#)



def generate_name(prompt):
    try:
        input_text = (
            "Eres el Asistente de Procesos de la Universidad Francisco Marroquín (UFM). "
            "Genera únicamente un título breve, profesional e institucional, de máximo 50 caracteres "
            "en español, basado en esta consulta relacionada con procesos administrativos: "
            f"{prompt}. "
            "No expliques nada, no uses comillas ni justificación, y asegúrate de que el título refleje el propósito de la consulta o el tipo de proceso (si es mencionado)."
        )
        response = modelNames.invoke(input_text)
        return response.content.strip()
    except Exception as e:
        return f"Error con la respuesta: {e}"




# --------------------------
# Modelo para citar documentos recuperados

class Citation(BaseModel):
    page_content: str
    metadata: Dict

def extract_citations(response: List[Dict]) -> List[Citation]:
    return [Citation(page_content=doc.page_content, metadata=doc.metadata) for doc in response]

# --------------------------



