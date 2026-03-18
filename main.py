from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return("регистрация")
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")
    email = data.get("email")

    return jsonify(
        {
            "username": username,
            "password": password,
            "email": email,
        }
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return('эта типа логин в аккаунт')

    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    return jsonify(
        {
            "username": username,
            "password": password,
        }
    )


@app.route("/logout", methods=["GET", "POST"])
def logout():
    if request.method == "GET":
        return('хз будет тут стрница или нет, но тут будет логаут')

    data = request.get_json(silent=True) or {}
    token = data.get("token")

    return jsonify({"token": token})


@app.route("/users", methods=["GET", "POST"])
def users():
    data = request.get_json(silent=True) or {}
    query = data.get("query")
    limit = data.get("limit")

    return jsonify(
        {
            "query": query,
            "limit": limit,
        }
    )


@app.route("/chats", methods=["GET", "POST"])
def chats():
    data = request.get_json(silent=True) or {}
    title = data.get("title")
    member_ids = data.get("member_ids")

    return jsonify(
        {
            "title": title,
            "member_ids": member_ids,
        }
    )


@app.route("/chats/<int:chat_id>/messages", methods=["GET", "POST"])
def chat_messages(chat_id):
    data = request.get_json(silent=True) or {}
    text = data.get("text")
    sender_id = data.get("sender_id")

    return jsonify(
        {
            "chat_id": chat_id,
            "text": text,
            "sender_id": sender_id,
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=14080, debug=True)
