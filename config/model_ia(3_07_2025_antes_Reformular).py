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
from langchain.callbacks import collect_runs




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



inference_profile3_5claudehaiku="us.anthropic.claude-3-5-haiku-20241022-v1:0"
inference_profile3claudehaiku="us.anthropic.claude-3-haiku-20240307-v1:0"
inference_profile3_5Sonnet="us.anthropic.claude-3-5-sonnet-20240620-v1:0"
inference_profile3_7Sonnet="us.anthropic.claude-3-7-sonnet-20250219-v1:0"


inference_profile3_7Sonnet="arn:aws:bedrock:us-east-1:552102268375:application-inference-profile/tcsgx7nj4mf1"



# Claude 3 Sonnet ID
model = ChatBedrock(
    client=bedrock_runtime,
    model_id=inference_profile3_7Sonnet,
    model_kwargs=model_kwargs,
        provider="anthropic"  

   # streaming=True
)


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


def create_prompt_template_procesos():
    return ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT_PROCESOS),
            MessagesPlaceholder(variable_name="historial"),
            ("human", "{question}")
        ]
    )

# Base de conocimiento en Bedrock
BASE_CONOCIMIENTOS_PROCESOS = "OWLYEEHPY5"

retriever = AmazonKnowledgeBasesRetriever(
    knowledge_base_id=BASE_CONOCIMIENTOS_PROCESOS,
    retrieval_config={"vectorSearchConfiguration": {"numberOfResults": 100}},


)



def generar_configuracion_retriever(codigos_activos: list) -> dict:
    config = {
        "vectorSearchConfiguration": {
            "numberOfResults": 100
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

def build_procesos_chain(codigos_activos: list):
    retriever = AmazonKnowledgeBasesRetriever(
        knowledge_base_id=BASE_CONOCIMIENTOS_PROCESOS,
        retrieval_config=generar_configuracion_retriever(codigos_activos)
    )

    prompt_template = create_prompt_template_procesos()

    chain = (
        RunnableParallel({
            "context": itemgetter("question") | retriever,
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
    inputs = {
        "question": question,
        "historial": history
    }
    return chain.stream(inputs)


inference_profile3_5Sonnet="arn:aws:bedrock:us-east-1:552102268375:application-inference-profile/sc2jrj3crjn0"


modelNames = ChatBedrock(
    client=bedrock_runtime,
    model_id=inference_profile3_5Sonnet,
    model_kwargs=model_kwargs,
    provider="anthropic"  
)



def generate_name(prompt):
    try:
        input_text = (
            "Eres el Asistente de Procesos de la Universidad Francisco Marroquín (UFM). "
            "Genera únicamente un título breve, profesional e institucional, de máximo 50 caracteres "
            "en español, basado en esta consulta relacionada con procesos administrativos: "
            f"{prompt}. "
            "No expliques nada, no uses comillas ni justificación, y asegúrate de que el título refleje el propósito o el tipo de proceso mencionado."
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



