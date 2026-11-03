from django.contrib.auth.hashers import MD5PasswordHasher


class CountingMD5PasswordHasher(MD5PasswordHasher):
    """Fast hasher that records how many times `verify` ran."""

    algorithm = "counting_md5"
    verify_calls = 0

    def verify(self, password, encoded):
        type(self).verify_calls += 1
        return super().verify(password, encoded)
