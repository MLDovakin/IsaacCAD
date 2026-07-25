from .null_backend import NullBackend


def get_backend(name: str = "null", **kwargs):
    if name == "null":
        return NullBackend()
    if name == "usd":
        from .usd_backend import UsdBackend
        return UsdBackend(**kwargs)
    raise ValueError(f"unknown backend {name!r}; use 'null' or 'usd'")


__all__ = ["get_backend", "NullBackend"]
