import boto3
import json
from botocore.exceptions import ClientError
from datetime import datetime
from boto3.dynamodb.conditions import Key, Attr
#import config.model_ia as model  # Para usar model.generate_name
import config.model_iacatching as model  # Para usar model.generate_name


# Inicializar recurso de DynamoDB
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table = dynamodb.Table("ProcesosSessionTable")

# Clave primaria: solo USER
def build_pk(user_id):
    return f"USER#{user_id}"


def save(chat_id, user_id, name, chat):
    item = {
        "PK": build_pk(user_id),
        "SK": f"CHAT#{chat_id}",
        "Name": name,
        "Chat": chat,
        "CreatedAt": datetime.utcnow().isoformat()
        # No necesitas guardar IsDeleted=False; si no existe, se asume activo
    }
    table.put_item(Item=item)


def edit(chat_id, chat, user_id):
    table.update_item(
        Key={"PK": build_pk(user_id), "SK": f"CHAT#{chat_id}"},
        UpdateExpression="SET Chat = :chat",
        ExpressionAttributeValues={":chat": chat}
    )


def getChats(user_id, include_deleted=False):
    """
    - Por defecto (include_deleted=False) NO devuelve chats eliminados lógicamente.
    - "Activo" = IsDeleted no existe, o IsDeleted=False.
    """
    try:
        params = {
            "KeyConditionExpression": Key("PK").eq(build_pk(user_id)),
            "ScanIndexForward": False
        }

        if not include_deleted:
            params["FilterExpression"] = Attr("IsDeleted").not_exists() | Attr("IsDeleted").eq(False)

        response = table.query(**params)
        data = response.get("Items", [])

        for item in data:
            chat = item.get("Chat")
            if isinstance(chat, str):
                try:
                    item["Chat"] = json.loads(chat)
                except json.JSONDecodeError:
                    item["Chat"] = []
            elif not chat:
                item["Chat"] = []

        data.sort(key=lambda x: x.get("CreatedAt", ""), reverse=True)
        return data

    except ClientError as e:
        print("Error en getChats:", e)
        return []


def delete(chat_id, user_id):
    """
    Soft delete: NO borra el item.
    Solo marca IsDeleted=True para ocultarlo en la UI y mantener métricas intactas.
    """
    table.update_item(
        Key={"PK": build_pk(user_id), "SK": f"CHAT#{chat_id}"},
        UpdateExpression="SET IsDeleted = :d, DeletedAt = :ts",
        ExpressionAttributeValues={
            ":d": True,
            ":ts": datetime.utcnow().isoformat()
        }
    )


def editName(chat_id, prompt, user_id):
    name = model.generate_name(prompt)
    table.update_item(
        Key={"PK": build_pk(user_id), "SK": f"CHAT#{chat_id}"},
        UpdateExpression="SET #n = :name",
        ExpressionAttributeNames={"#n": "Name"},
        ExpressionAttributeValues={":name": name}
    )


def editNameManual(chat_id, new_name, user_id):
    table.update_item(
        Key={"PK": build_pk(user_id), "SK": f"CHAT#{chat_id}"},
        UpdateExpression="SET #n = :name",
        ExpressionAttributeNames={"#n": "Name"},
        ExpressionAttributeValues={":name": new_name}
    )


def getNameChat(chat_id, user_id):
    try:
        response = table.get_item(
            Key={"PK": build_pk(user_id), "SK": f"CHAT#{chat_id}"}
        )
        return response["Item"]["Name"]
    except KeyError:
        return None
