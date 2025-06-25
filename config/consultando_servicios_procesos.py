import boto3

regions = ['us-east-1', 'us-east-2']
tag_key = 'chatbot'
tag_value = 'PROCESOS'

for region in regions:
    #print(f"\n Recursos en la región: {region}")
    #print("-" * 80)

    client = boto3.client('resourcegroupstaggingapi', region_name=region)

    response = client.get_resources(
        TagFilters=[{
            'Key': tag_key,
            'Values': [tag_value]
        }]
    )

    for resource in response['ResourceTagMappingList']:
        arn = resource['ResourceARN']
        tags = {tag['Key']: tag['Value'] for tag in resource.get('Tags', [])}
        componente_chatbot = tags.get('componente_chatbot', 'N/A')

        print(f"    Recurso: {arn}")
        print(f"    Descripción: {componente_chatbot}")
        print("-" * 80)
