import requests

BOT_TOKEN = "7555314078:AAE7aFR3X2J2qc42XgcsXCR8wQT3IvGzdn8"

# ������� webhook
response = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true")
print(response.json())

# ��������� ��� ����������
response = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo")
print(response.json())