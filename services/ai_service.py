import openai
from flask import current_app

def ask_gpt(question, conversation_history=None, user_role="client"):
    openai.api_key = current_app.config.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        return "Ключ OpenAI не налаштований. Зверніться до адміністратора."

    if conversation_history is None:
        conversation_history = []

    if user_role == "doctor":
        system_prompt = """Ти досвідчений ветеринарний лікар. 
        Можеш давати рекомендації щодо лікування, дозувань, діагностики. 
        Але завжди нагадуй, що остаточний діагноз ставиться після очного прийому."""
    else:
        system_prompt = """Ти ввічливий асистент ветеринарної клініки. 
        НІКОЛИ не давай дозувань ліків, не стави діагнозів, не призначай лікування.
        Завжди рекомендуй звернутися до лікаря для очного огляду.
        Відповідай на загальні питання про догляд, харчування, поведінку тварин."""

    # Фільтр заборонених слів для клієнтів
    if user_role != "doctor":
        forbidden_words = ["доза", "мг", "міліграм", "антибіотик", "лікування", "таблетка", "укол", "препарат"]
        question_lower = question.lower()
        for word in forbidden_words:
            if word in question_lower:
                return "⚠️ Вибачте, я не можу давати рекомендації щодо лікування або дозувань. Будь ласка, зверніться до лікаря особисто."

    messages = [
        {"role": "system", "content": system_prompt},
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