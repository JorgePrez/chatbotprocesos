import csv

# 🔧 Configuración
table_name = 'CHATBOT_CENTRO_COSTOS'
input_file = 'chabot_centro_costos_compras.csv'
output_file = 'inserts_chatbot_centro_costos.sql'

def escape(value):
    if value is None or value.strip() == "":
        return "NULL"
    value = value.replace("'", "''")
    if '&' in value:
        parts = value.split('&')
        parts = [f"'{part.strip()}'" for part in parts]
        return ' || CHR(38) || '.join(parts)
    return f"'{value}'"

with open(input_file, newline='', encoding='utf-8') as csvfile, open(output_file, 'w', encoding='utf-8') as sqlfile:
    reader = csv.DictReader(csvfile)

    for row in reader:
        nombre_mostrar = escape(row['NOMBRE_MOSTRAR'])
        codigo = escape(row['CODIGO'])
        centro_costo = row['CENTRO_COSTO'] or 'NULL'
        doc_pasos = escape(row.get('ID_SUBCARPETA_DOCUMENTO_PASOS', ''))
        flujograma = escape(row.get('ID_SUBCARPETA_FLUJOGRAMA', ''))
        bucket = escape(row.get('S3_BEDROCK_BUCKET', ''))
        datasource = escape(row.get('DATASOURCE', ''))

        insert_stmt = (
            f"INSERT INTO {table_name} "
            f"(NOMBRE_MOSTRAR, CODIGO, CENTRO_COSTO, ID_SUBCARPETA_DOCUMENTO_PASOS, "
            f"ID_SUBCARPETA_FLUJOGRAMA, S3_BEDROCK_BUCKET, DATASOURCE) "
            f"VALUES ({nombre_mostrar}, {codigo}, {centro_costo}, {doc_pasos}, {flujograma}, {bucket}, {datasource});\n"
        )
        sqlfile.write(insert_stmt)

print(f"✅ Script generado: {output_file}")
