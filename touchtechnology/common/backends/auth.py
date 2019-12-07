from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.hashers import UNUSABLE_PASSWORD_PREFIX


class UserSubclassBackend(ModelBackend):
    def get_user(self, user_id):
        UserModel = get_user_model()
        try:
            return UserModel.objects.exclude(
                password__startswith=UNUSABLE_PASSWORD_PREFIX).get(pk=user_id)
        except UserModel.DoesNotExist:
            return None


class EmailUserSubclassBackend(UserSubclassBackend):
    def authenticate(self, request, username=None, password=None):
        UserModel = get_user_model()
        try:
            # Check if the 'username' is actually an email address
            if username is not None and "@" in username:
                # If there is more than one user account with the same email
                # address on file we'll step through them. Particularly of use
                # when we've switched to email based authentication after
                # previously having used usernames.
                for user in UserModel.objects.filter(email=username):
                    if user.check_password(password):
                        return user
        except UserModel.DoesNotExist:
            pass
        return None
