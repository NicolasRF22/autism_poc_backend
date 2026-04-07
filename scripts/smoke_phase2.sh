#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:5000/api}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-}"

if [[ -z "$ADMIN_PASS" ]]; then
  echo "Erro: defina ADMIN_PASS para executar o smoke test"
  exit 1
fi

json_extract() {
  local json_input="$1"
  local expr="$2"
  python3 -c 'import json,sys
expr=sys.argv[1]
raw=sys.argv[2]
try:
  data=json.loads(raw or "null")
except Exception:
  print("")
  raise SystemExit(0)
cur=data
for part in expr.split("."):
  if not part:
    continue
  if isinstance(cur, dict):
    cur=cur.get(part)
  else:
    cur=None
    break
if cur is None:
  print("")
elif isinstance(cur, (dict, list)):
  print(json.dumps(cur, ensure_ascii=False))
else:
  print(cur)
' "$expr" "$json_input"
}

json_len() {
  local json_input="$1"
  python3 -c 'import json,sys
raw=sys.argv[1]
try:
  data=json.loads(raw or "null")
except Exception:
  print(0)
  raise SystemExit(0)
print(len(data) if isinstance(data, (list, dict)) else 0)
' "$json_input"
}

echo "[1/13] Login"
TOKEN=$(curl -s -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}")
TOKEN=$(json_extract "$TOKEN" "token")

if [[ -z "$TOKEN" || "$TOKEN" == "null" ]]; then
  echo "Falha no login"
  exit 1
fi

echo "[2/13] Criando escola"
SCHOOL_RESP=$(curl -s -X POST "$API_BASE/schools" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name":"Escola Teste Fase2",
    "cnpj":"00.000.000/0002-00",
    "institution_type":"Municipal",
    "address":{"city":"Itajubá"}
  }')
SCHOOL_ID=$(json_extract "$SCHOOL_RESP" "school.id")

if [[ -z "$SCHOOL_ID" || "$SCHOOL_ID" == "null" ]]; then
  echo "Falha ao criar escola"
  echo "$SCHOOL_RESP"
  exit 1
fi

echo "[3/13] Criando aluno"
STUDENT_RESP=$(curl -s -X POST "$API_BASE/students" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\":\"Aluno Teste Fase2\",
    \"age\":\"10\",
    \"school_id\":\"$SCHOOL_ID\",
    \"school_name\":\"Escola Teste Fase2\",
    \"grade\":\"5\",
    \"class\":\"A\"
  }")
STUDENT_ID=$(json_extract "$STUDENT_RESP" "student.id")

if [[ -z "$STUDENT_ID" || "$STUDENT_ID" == "null" ]]; then
  echo "Falha ao criar aluno"
  echo "$STUDENT_RESP"
  exit 1
fi

echo "[4/13] Criando entrada de diário"
DIARY_RESP=$(curl -s -X POST "$API_BASE/diary/entries" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"student_id\":\"$STUDENT_ID\",
    \"student_name\":\"Aluno Teste Fase2\",
    \"teachers\":[\"Docente Fase2\"],
    \"diary_date\":\"2026-04-06\",
    \"answers\":{\"q1\":\"ok\"},
    \"open_obs\":\"observação inicial\",
    \"status\":\"final\",
    \"source\":\"manual\"
  }")
DIARY_ID=$(json_extract "$DIARY_RESP" "entry.id")

if [[ -z "$DIARY_ID" || "$DIARY_ID" == "null" ]]; then
  echo "Falha ao criar diário"
  echo "$DIARY_RESP"
  exit 1
fi

echo "[5/13] Lendo entradas de diário por aluno"
DIARY_GET=$(curl -s "$API_BASE/diary/entries/Aluno%20Teste%20Fase2?student_id=$STUDENT_ID" \
  -H "Authorization: Bearer $TOKEN")
if [[ "$(json_len "$DIARY_GET")" == "0" ]]; then
  echo "Falha ao ler diário por aluno"
  echo "$DIARY_GET"
  exit 1
fi

echo "[6/13] Atualizando entrada de diário"
DIARY_UPD_RESP=$(curl -s -X PUT "$API_BASE/diary/entries/$DIARY_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"student_id\":\"$STUDENT_ID\",
    \"teachers\":[\"Docente Fase2\",\"Docente Fase2B\"],
    \"diary_date\":\"2026-04-06\",
    \"answers\":{\"q1\":\"ok\",\"q2\":\"ajustado\"},
    \"open_obs\":\"observação atualizada\",
    \"status\":\"final\",
    \"source\":\"manual\"
  }")

if [[ "$(json_extract "$DIARY_UPD_RESP" "entry.id")" != "$DIARY_ID" ]]; then
  echo "Falha ao atualizar diário"
  echo "$DIARY_UPD_RESP"
  exit 1
fi

echo "[7/13] Criando PDI"
PDI_RESP=$(curl -s -X POST "$API_BASE/pdi" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"student_id\":\"$STUDENT_ID\",
    \"student_name\":\"Aluno Teste Fase2\",
    \"birth_date\":\"2015-01-01\",
    \"guardians\":[\"Responsável 1\"],
    \"diagnosis\":\"TEA\",
    \"class\":\"5A\",
    \"teachers\":[\"Docente Fase2\"],
    \"trimesters\":{
      \"trimester_1\":{\"goals\":\"meta 1\"},
      \"trimester_2\":{\"goals\":\"meta 2\"},
      \"trimester_3\":{\"goals\":\"meta 3\"}
    }
  }")
PDI_ID=$(json_extract "$PDI_RESP" "pdi.id")

if [[ -z "$PDI_ID" || "$PDI_ID" == "null" ]]; then
  echo "Falha ao criar PDI"
  echo "$PDI_RESP"
  exit 1
fi

echo "[8/13] Lendo PDI por ID"
PDI_GET=$(curl -s "$API_BASE/pdi/id/$PDI_ID" \
  -H "Authorization: Bearer $TOKEN")
if [[ "$(json_extract "$PDI_GET" "id")" != "$PDI_ID" ]]; then
  echo "Falha ao ler PDI"
  echo "$PDI_GET"
  exit 1
fi

echo "[9/13] Atualizando PDI"
PDI_UPD_RESP=$(curl -s -X PUT "$API_BASE/pdi/$PDI_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"student_id\":\"$STUDENT_ID\",
    \"student_name\":\"Aluno Teste Fase2\",
    \"birth_date\":\"2015-01-01\",
    \"guardians\":[\"Responsável 1\",\"Responsável 2\"],
    \"diagnosis\":\"TEA\",
    \"class\":\"5A\",
    \"teachers\":[\"Docente Fase2\",\"Docente Fase2B\"],
    \"trimesters\":{
      \"trimester_1\":{\"goals\":\"meta 1\"},
      \"trimester_2\":{\"goals\":\"meta 2 ajustada\"},
      \"trimester_3\":{\"goals\":\"meta 3\"}
    }
  }")

if [[ "$(json_extract "$PDI_UPD_RESP" "pdi.id")" != "$PDI_ID" ]]; then
  echo "Falha ao atualizar PDI"
  echo "$PDI_UPD_RESP"
  exit 1
fi

echo "[10/13] Validando listagens de diário e PDI"
DIARY_LIST=$(curl -s "$API_BASE/diary/students" -H "Authorization: Bearer $TOKEN")
PDI_LIST=$(curl -s "$API_BASE/pdi/all" -H "Authorization: Bearer $TOKEN")
if [[ "$(json_len "$DIARY_LIST")" == "0" ]]; then
  echo "Falha na listagem de diário"
  echo "$DIARY_LIST"
  exit 1
fi
if [[ "$(json_len "$PDI_LIST")" == "0" ]]; then
  echo "Falha na listagem de PDI"
  echo "$PDI_LIST"
  exit 1
fi

echo "[11/13] Removendo diário"
DIARY_DEL=$(curl -s -X DELETE "$API_BASE/diary/entries/$DIARY_ID" -H "Authorization: Bearer $TOKEN")
if [[ -z "$(json_extract "$DIARY_DEL" "message")" ]]; then
  echo "Falha ao remover diário"
  echo "$DIARY_DEL"
  exit 1
fi

echo "[12/13] Removendo PDI"
PDI_DEL=$(curl -s -X DELETE "$API_BASE/pdi/$PDI_ID" -H "Authorization: Bearer $TOKEN")
if [[ -z "$(json_extract "$PDI_DEL" "message")" ]]; then
  echo "Falha ao remover PDI"
  echo "$PDI_DEL"
  exit 1
fi

echo "[13/13] Limpando aluno e escola"
curl -s -X DELETE "$API_BASE/students/$STUDENT_ID" -H "Authorization: Bearer $TOKEN" >/dev/null
curl -s -X DELETE "$API_BASE/schools/$SCHOOL_ID" -H "Authorization: Bearer $TOKEN" >/dev/null

echo "Smoke test da Fase 2 concluído com sucesso"
