@client_bp.route('/api/my-profile')
def my_profile():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify({"phone": user.phone if user else ""})
    profile = enote.get_client_profile(user.enote_guid)
    full_name = f"{profile.get('surname','')} {profile.get('firstName','')} {profile.get('patronymic','')}".strip()
    return jsonify({
        "full_name": full_name,
        "phone": user.phone,
        "email": user.email
    })
