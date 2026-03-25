from flask_login import UserMixin


class User(UserMixin):
    def __init__(self, user_data: dict):
        self.id    = user_data["id"]
        self.name  = user_data["name"]
        self.email = user_data["email"]
        self.role  = user_data["role"]
