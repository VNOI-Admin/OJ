from oauth2_provider.oauth2_validators import OAuth2Validator


class VNOIOAuthValidator(OAuth2Validator):
    def get_additional_claims(self, request):
        user = request.user
        return {
            'email': user.email,
            'given_name': user.first_name,
            'username': user.username,
        }
