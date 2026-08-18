import boto3

# cliente Bedrock
client = boto3.client("bedrock", region_name="us-east-1")

# Parámetros del nuevo perfil
inference_profile_name = "CHH-Global-crossregion-claudesonnet5"
description = "CHH usando Claude Sonnet 5 "


model_source = {
    "copyFrom": "arn:aws:bedrock:us-east-1:552102268375:inference-profile/global.anthropic.claude-sonnet-5"
}
tags = [
        {"key": "chatbot", "value": "CHH"},
        {"key": "componente_chatbot", "value": "modelo_lenguaje_claude5sonnet"}
]

# Crear el perfil
response = client.create_inference_profile(
    inferenceProfileName=inference_profile_name,
    description=description,
    modelSource=model_source,
    tags=tags
)

# Mostrar el ARN del nuevo perfil
print("Inference profile creado exitosamente:")
print("ARN:", response["inferenceProfileArn"])

#ARN: arn:aws:bedrock:us-east-1:552102268375:application-inference-profile/h5urspjrj64d  18-08-2026
