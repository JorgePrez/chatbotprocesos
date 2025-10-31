
# 🚀 Deploy de Streamlit como servicio en Amazon Linux 2023 (ARM / Graviton)

Este documento describe el proceso completo para migrar y ejecutar una aplicación Streamlit como servicio en una instancia **Amazon EC2 t4g.large (Graviton ARM64)** con **Amazon Linux 2023**, asegurando ejecución automática incluso después de reinicios del servidor.

---

## 📌 Requisitos previos

- Instancia EC2 con Amazon Linux 2023 (ARM / Graviton)
- Python 3.11.6 instalado manualmente
- AWS CLI configurado (`aws configure`)
- Acceso al repositorio del proyecto `chatbotprocesos`
- Archivo `requirements_py311.txt` exportado desde el servidor anterior

---

## 1. Clonar el proyecto

cd /home/ec2-user
git clone https://github.com/JorgePrez/chatbotprocesos.git
cd chatbotprocesos

---

## 2. Instalar dependencias

aws s3 cp s3://configyaml/REQUIREMENTS/migracion_n8n_2025/requirements_py311.txt .
python3.11 -m pip install -r requirements_py311.txt

---

## 3. Probar Streamlit manualmente

python3.11 -m streamlit run chatbot_embebido_n8n_modularizado.py --server.port 8090

Si carga correctamente → continuar.

---

## 4. Crear script de arranque

📍 Archivo: /home/ec2-user/start_streamlit_procesos.sh

#!/bin/bash
cd /home/ec2-user/chatbotprocesos
/usr/local/bin/python3.11 -m streamlit run chatbot_embebido_n8n_modularizado.py --server.port 8090

Dar permisos:

sudo chmod +x /home/ec2-user/start_streamlit_procesos.sh

---

## 5. Crear servicio systemd

📍 Archivo: /etc/systemd/system/streamlit_procesos.service

[Unit]
Description=Chatbot Procesos - Streamlit
After=network.target

[Service]
ExecStart=/home/ec2-user/start_streamlit_procesos.sh
Restart=always
RestartSec=3
User=ec2-user
WorkingDirectory=/home/ec2-user/chatbotprocesos

[Install]
WantedBy=multi-user.target

---

## 6. Activar y ejecutar el servicio

sudo systemctl daemon-reload
sudo systemctl enable streamlit_procesos.service
sudo systemctl start streamlit_procesos.service
sudo systemctl status streamlit_procesos.service

Salida esperada:

Active: active (running)

---

## 7. Validar reinicio automático

sudo reboot
# reconectar al servidor, luego:
systemctl status streamlit_procesos.service

Debe seguir en active (running) sin intervención manual.

---

## 8. Logs del servicio

sudo journalctl -u streamlit_procesos.service -f

---

## 9. Opcional: habilitar log persistente

Editar script:

/usr/local/bin/python3.11 -m streamlit run chatbot_embebido_n8n_modularizado.py --server.port 8090 >> /home/ec2-user/streamlit.log 2>&1

Para leer logs:

tail -f /home/ec2-user/streamlit.log

---

## 10. Comandos útiles

| Acción                   | Comando                                            |
|--------------------------|-----------------------------------------------------|
| Reiniciar servicio       | sudo systemctl restart streamlit_procesos.service  |
| Detener servicio         | sudo systemctl stop streamlit_procesos.service     |
| Ver estado               | sudo systemctl status streamlit_procesos.service   |
| Deshabilitar en arranque | sudo systemctl disable streamlit_procesos.service  |

---

## 🔍 Notas

- El .env no se incluye en el repo — Streamlit lo carga automáticamente desde el directorio del proyecto.
- El servicio corre como ec2-user, no root.
- Puerto configurado: 8090.
- Python utilizado: /usr/local/bin/python3.11.

---

## ✅ Estado final

| Componente                                 | Estado |
|---------------------------------------------|--------|
| App Streamlit                              | ✔️ corriendo como servicio |
| Arranca al iniciar servidor                | ✔️ enabled |
| Proyecto y script en /home/ec2-user        | ✔️ |
| Servicio supervisado por systemd           | ✔️ |