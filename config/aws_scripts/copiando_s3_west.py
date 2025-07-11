import boto3
from botocore.exceptions import ClientError

buckets = {
    "n8nprocesosextraido1": "n8nprocesosextraido1-west",
    "n8nprocesosextraido2": "n8nprocesosextraido2-west",
    "n8nprocesosextraido3": "n8nprocesosextraido3-west",
    "n8nprocesosextraido4": "n8nprocesosextraido4-west",
    "n8nprocesosextraido5": "n8nprocesosextraido5-west",
}

s3_east = boto3.client("s3", region_name="us-east-1")
s3_west = boto3.client("s3", region_name="us-west-2")

for source_bucket, dest_bucket in buckets.items():
    print(f"🔄 Copiando de {source_bucket} → {dest_bucket}...")

    # Crear bucket destino si no existe
    try:
        s3_west.head_bucket(Bucket=dest_bucket)
        print(f"✅ Bucket {dest_bucket} ya existe.")
    except ClientError:
        print(f"🪣 Creando bucket {dest_bucket} en us-west-2...")
        s3_west.create_bucket(
            Bucket=dest_bucket,
            CreateBucketConfiguration={'LocationConstraint': 'us-west-2'}
        )

    # Listar y copiar archivos
    paginator = s3_east.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=source_bucket):
        for obj in page.get('Contents', []):
            key = obj['Key']
            print(f"  📁 Copiando: {key}")

            copy_source = {
                'Bucket': source_bucket,
                'Key': key
            }

            s3_west.copy_object(
                Bucket=dest_bucket,
                Key=key,
                CopySource=copy_source
            )

    print(f"✅ Finalizado {source_bucket} → {dest_bucket}\n")

print("🎉 Todos los buckets fueron copiados.")
