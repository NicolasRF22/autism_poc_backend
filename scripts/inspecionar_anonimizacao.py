"""
Inspeciona o contexto anonimizado enviado ao Gemini para um aluno.

Uso:
    python scripts/inspecionar_anonimizacao.py <student_id> [--modo chat|pei] [--mensagem "..."]

Exemplos:
    python scripts/inspecionar_anonimizacao.py d7d6bbe7-d7aa-4ba2-95e8-2ee984b15ee9
    python scripts/inspecionar_anonimizacao.py d7d6bbe7-d7aa-4ba2-95e8-2ee984b15ee9 --modo chat --mensagem "Quais sao os pontos fortes?"
    python scripts/inspecionar_anonimizacao.py d7d6bbe7-d7aa-4ba2-95e8-2ee984b15ee9 --modo pei
"""

import argparse
import json
import sys
import urllib.request
import urllib.error

BASE_URL = "http://localhost:5000"
USERNAME = "admin"
PASSWORD = "admin123"

SEPARADOR = "-" * 70


def _post(path: str, payload: dict, token: str = "") -> dict:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE_URL}{path}", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def login() -> str:
    data = _post("/api/auth/login", {"username": USERNAME, "password": PASSWORD})
    token = data.get("token", "")
    if not token:
        print(f"[ERRO] Login falhou: {data}")
        sys.exit(1)
    return token


def _print_mapa(name_map: dict) -> None:
    if not name_map:
        print("  (vazio)")
        return
    for uuid, nome in name_map.items():
        print(f"  {uuid}  ->  {nome}")


def _verificar_vazamentos(ctx: str, name_map: dict) -> list[str]:
    return [nome for nome in name_map.values() if nome and nome in ctx]


def _secao(titulo: str) -> None:
    print()
    print(SEPARADOR)
    print(f"  {titulo}")
    print(SEPARADOR)


def inspecionar_chat(token: str, student_id: str, mensagem: str) -> None:
    _secao("MODO: CHAT  (dry_run=True)")
    payload = {
        "student_id": student_id,
        "message": mensagem,
        "dry_run": True,
        "selected_sources": {
            "student_pre_registration": True,
            "school_pre_registration": True,
            "pdi": True,
            "diary": True,
        },
    }
    r = _post("/api/rag/chat", payload, token)

    if not r.get("dry_run"):
        print(f"[ERRO] Resposta inesperada: {r}")
        return

    name_map = r.get("deanonymization_map", {})
    ctx = r.get("anonymized_context", "") or ""
    vazamentos = _verificar_vazamentos(ctx, name_map)

    print()
    print(">> MAPA DE DE-ANONIMIZACAO (UUID -> Nome real)")
    _print_mapa(name_map)

    print()
    print(f">> VAZAMENTOS DE NOME NO CONTEXTO: {'NENHUM' if not vazamentos else ', '.join(vazamentos)}")

    print()
    print(">> SYSTEM PROMPT (primeiros 300 chars)")
    print(r.get("system_prompt_preview", "(nao disponivel)")[:300])

    print()
    print(">> CONTEXTO ANONIMIZADO ENVIADO AO GEMINI")
    print(ctx[:2000] if ctx else "(vazio)")
    if len(ctx) > 2000:
        print(f"\n  ... [{len(ctx) - 2000} chars omitidos]")

    print()
    print(">> MENSAGEM DO USUARIO")
    print(r.get("message", ""))

    print()
    print(r.get("note", ""))


def inspecionar_pei(token: str, student_id: str) -> None:
    _secao("MODO: PEI  (dry_run=True)")
    payload = {
        "student_id": student_id,
        "dry_run": True,
        "selected_sources": {
            "student_pre_registration": True,
            "school_pre_registration": True,
            "pdi": True,
            "diary": True,
        },
    }
    r = _post("/api/rag/generate-pei", payload, token)

    if not r.get("dry_run"):
        print(f"[ERRO] Resposta inesperada: {r}")
        return

    name_map = r.get("deanonymization_map", {})
    ctx = r.get("anonymized_context", "") or ""
    vazamentos = _verificar_vazamentos(ctx, name_map)

    print()
    print(">> MAPA DE DE-ANONIMIZACAO (UUID -> Nome real)")
    _print_mapa(name_map)

    print()
    print(f">> VAZAMENTOS DE NOME NO CONTEXTO: {'NENHUM' if not vazamentos else ', '.join(vazamentos)}")

    print()
    print(">> PROMPT COMPLETO ENVIADO AO GEMINI (primeiros 1500 chars)")
    prompt = r.get("full_prompt_preview", "") or ""
    print(prompt[:1500])
    if len(prompt) > 1500:
        print(f"\n  ... [{len(prompt) - 1500} chars omitidos — total {len(prompt)} chars]")

    print()
    print(r.get("note", ""))


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspeciona contexto anonimizado enviado ao Gemini")
    parser.add_argument("student_id", help="UUID do aluno")
    parser.add_argument("--modo", choices=["chat", "pei", "ambos"], default="ambos",
                        help="Qual endpoint inspecionar (padrao: ambos)")
    parser.add_argument("--mensagem", default="Quais sao os pontos fortes deste aluno?",
                        help="Mensagem usada no dry run do chat")
    args = parser.parse_args()

    print(f"Conectando em {BASE_URL} como '{USERNAME}'...")
    token = login()
    print("Login OK.")

    if args.modo in ("chat", "ambos"):
        inspecionar_chat(token, args.student_id, args.mensagem)

    if args.modo in ("pei", "ambos"):
        inspecionar_pei(token, args.student_id)

    print()
    print(SEPARADOR)
    print("  Inspecao concluida.")
    print(SEPARADOR)


if __name__ == "__main__":
    main()
