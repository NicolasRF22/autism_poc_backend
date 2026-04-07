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

echo "[1/7] Login"
LOGIN_RESP=$(curl -s -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}")
TOKEN=$(json_extract "$LOGIN_RESP" "token")

if [[ -z "$TOKEN" || "$TOKEN" == "null" ]]; then
  echo "Falha no login"
  exit 1
fi

echo "[2/7] Criando escola"
SCHOOL_RESP=$(curl -s -X POST "$API_BASE/schools" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name":"Escola Teste Fase1",
    "cnpj":"00.000.000/0001-00",
    "institution_type":"Municipal",
    "address":{"city":"Itajubá"}
  }')
SCHOOL_ID=$(json_extract "$SCHOOL_RESP" "school.id")

if [[ -z "$SCHOOL_ID" || "$SCHOOL_ID" == "null" ]]; then
  echo "Falha ao criar escola"
  echo "$SCHOOL_RESP"
  exit 1
fi

echo "[3/7] Criando aluno"
STUDENT_RESP=$(curl -s -X POST "$API_BASE/students" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\":\"Aluno Teste Fase1\",
    \"age\":\"10\",
    \"school_id\":\"$SCHOOL_ID\",
    \"school_name\":\"Escola Teste Fase1\",
    \"grade\":\"5\",
    \"class\":\"A\"
  }")
STUDENT_ID=$(json_extract "$STUDENT_RESP" "student.id")

if [[ -z "$STUDENT_ID" || "$STUDENT_ID" == "null" ]]; then
  echo "Falha ao criar aluno"
  echo "$STUDENT_RESP"
  exit 1
fi

echo "[4/7] Criando docente"
TEACHER_RESP=$(curl -s -X POST "$API_BASE/teachers" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name":"Docente Teste Fase1",
    "school_name":"Escola Teste Fase1",
    "specialization":"AEE"
  }')
TEACHER_ID=$(json_extract "$TEACHER_RESP" "teacher.id")

if [[ -z "$TEACHER_ID" || "$TEACHER_ID" == "null" ]]; then
  echo "Falha ao criar docente"
  echo "$TEACHER_RESP"
  exit 1
fi

echo "[5/7] Validando listagens"
S_COUNT=$(json_len "$(curl -s "$API_BASE/schools" -H "Authorization: Bearer $TOKEN")")
ST_COUNT=$(json_len "$(curl -s "$API_BASE/students" -H "Authorization: Bearer $TOKEN")")
T_COUNT=$(json_len "$(curl -s "$API_BASE/teachers" -H "Authorization: Bearer $TOKEN")")

echo "Escolas:  $S_COUNT"
echo "Alunos:   $ST_COUNT"
echo "Docentes: $T_COUNT"

echo "[6/7] Limpando registros de teste"
curl -s -X DELETE "$API_BASE/students/$STUDENT_ID" -H "Authorization: Bearer $TOKEN" >/dev/null
curl -s -X DELETE "$API_BASE/teachers/$TEACHER_ID" -H "Authorization: Bearer $TOKEN" >/dev/null
curl -s -X DELETE "$API_BASE/schools/$SCHOOL_ID" -H "Authorization: Bearer $TOKEN" >/dev/null

echo "[7/7] Smoke test da Fase 1 concluído com sucesso"
