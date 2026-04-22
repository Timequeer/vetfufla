import openai
from flask import current_app

def ask_gpt(question, conversation_history=None):
    openai.api_key = current_app.config.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        return "Ключ OpenAI не налаштований. Зверніться до адміністратора."

    if conversation_history is None:
        conversation_history = []

    messages = [
        {"role": "system", "content": "Ти ввічливий асистент ветеринарної клініки. Відповідай на запитання про здоров'я тварин, записи, ліки, але при серйозних симптомах ради звернутися до лікаря."},
        *conversation_history,
        {"role": "user", "content": question}
    ]

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Помилка AI: {str(e)}"