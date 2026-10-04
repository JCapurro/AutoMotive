"""Check the worker's LLM configuration without API calls or database access.

    cd worker
    python -m tools.check_llm
"""
from __future__ import annotations

import config
from llm import build_provider
from llm.provider import LLMError


def main() -> int:
    if config.LLM_PROVIDER == "openai" and not config.OPENAI_API_KEY:
        print("Falta OPENAI_API_KEY en el .env de la raíz del proyecto.")
        return 1
    try:
        provider = build_provider()
    except (LLMError, ValueError) as error:
        print(str(error))
        return 1
    print(f"Configuración lista: {provider.name} (timeout {config.LLM_TIMEOUT_SECONDS:g} s).")
    print("No se llamó a la API; acceso, saldo y calidad del modelo aún no verificados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
