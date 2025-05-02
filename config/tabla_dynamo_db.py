

import boto3

dynamodb = boto3.resource("dynamodb")
client = boto3.client("sts")

try:
    # Crear la tabla DynamoDB
    table = dynamodb.create_table(
        TableName="ProcesosSessionTable",
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},   # Partition key
            {"AttributeName": "SK", "KeyType": "RANGE"}   # Sort key
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Esperar a que la tabla exista
    table.meta.client.get_waiter("table_exists").wait(TableName="ProcesosSessionTable")

    # Mostrar datos básicos de la tabla
    print(f"Tabla creada: {table.table_name}")
    print(f"Ítems actuales: {table.item_count}")

except Exception as e:
    print("Error al crear la tabla:", e)
