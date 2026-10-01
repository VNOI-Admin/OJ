from oauth2_provider.oauth2_validators import OAuth2Validator


class VNOIOAuthValidator(OAuth2Validator):
    oidc_claim_scope = OAuth2Validator.oidc_claim_scope.copy().update({
        'permissions': 'profile',
    })

    def get_additional_claims(self, request):
        user = request.user
        return {
            'email': user.email,
            'given_name': user.first_name,
            'preferred_username': user.username,
            'permissions': list(user.get_all_permissions()),
        }
