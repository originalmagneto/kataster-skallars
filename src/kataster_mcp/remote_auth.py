"""Verify opaque OAuth tokens with the explicitly configured SKALLARS issuer."""

import time
from urllib.parse import urlsplit

import httpx


class OAuth:
    def __init__(self, issuer: str, secret: str, resource: str):
        parsed = urlsplit(issuer)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
        ):
            raise ValueError("OAuth issuer must be an HTTPS origin")
        if not secret:
            raise ValueError("OAuth resource credential required")
        self.issuer, self.secret, self.resource = issuer, secret, resource
        self.client = httpx.AsyncClient(timeout=5, follow_redirects=False)

    async def tenant(self, token: str) -> str | None:
        from .remote import TENANT

        if not token or len(token) > 4096:
            return None
        try:
            response = await self.client.post(
                self.issuer + "/resource/introspect",
                headers={"Authorization": f"Bearer {self.secret}"},
                data={"resource": self.resource, "token": token},
            )
            response.raise_for_status()
            claims = response.json()
            if (
                claims.get("active") is True
                and claims.get("iss") == self.issuer
                and claims.get("aud") == self.resource
                and isinstance(claims.get("exp"), (int, float))
                and claims["exp"] > time.time()
                and isinstance(claims.get("sub"), str)
                and claims["sub"]
                and isinstance(claims.get("scope"), str)
                and "mcp:tools" in claims["scope"].split()
                and isinstance(claims.get("tenant"), str)
                and TENANT.fullmatch(claims["tenant"])
            ):
                return claims["tenant"]
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            pass
        return None
