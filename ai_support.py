import openai
from flask import current_app, session

def ask_gpt(question, conversation_history=None):
    """
    Отправляет вопрос в OpenAI GPT и возвращает ответ
    """
    # Получаем API ключ из конфигурации Flask
    openai.api_key = current_app.config.get("OPENAI_API_KEY", "")
    
    # Если ключа нет, возвращаем сообщение об ошибке
    if not openai.api_key:
        return "Ключ OpenAI не налаштований. Зверніться до адміністратора."
    
    # Если нет истории диалога, создаем пустую
    if conversation_history is None:
        conversation_history = []
    
    # Формируем сообщения для GPT
    messages = [
        {"role": "system", "content": "Ти ввічливий асистент ветеринарної клініки. Відповідай на запитання про здоров'я тварин, записи, ліки, але при серйозних симптомах ради звернутися до лікаря."},
        *conversation_history,
        {"role": "user", "content": question}
    ]
    
    try:
        # Отправляем запрос к OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        # Возвращаем ответ
        return response.choices[0].message.content
    except Exception as e:
        # Если ошибка, возвращаем сообщение об ошибке
        return f"Помилка AI: {str(e)}"