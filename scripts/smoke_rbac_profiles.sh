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

require_status() {
  local got="$1"
  local want="$2"
  local context="$3"
  if [[ "$got" != "$want" ]]; then
    echo "Falha: $context (esperado=$want, obtido=$got)"
    exit 1
  fi
}

request() {
  local method="$1"
  local url="$2"
  local token="${3:-}"
  local body="${4:-}"
  token="$(printf '%s' "$token" | tr -d '\r\n')"
  local headers=(-H "Content-Type: application/json")
  if [[ -n "$token" ]]; then
    headers+=(-H "Authorization: Bearer $token")
  fi

  if [[ -n "$body" ]]; then
    curl -sS --connect-timeout 5 --max-time 30 -w "\n%{http_code}" -X "$method" "$url" "${headers[@]}" -d "$body"
  else
    curl -sS --connect-timeout 5 --max-time 30 -w "\n%{http_code}" -X "$method" "$url" "${headers[@]}"
  fi
}

split_response() {
  local raw="$1"
  local status
  status=$(echo "$raw" | tail -n1)
  local body
  body=$(echo "$raw" | sed '$d')
  echo "$status"
  echo "$body"
}

login() {
  local username="$1"
  local password="$2"
  local raw
  raw=$(request POST "$API_BASE/auth/login" "" "{\"username\":\"$username\",\"password\":\"$password\"}")
  local parsed
  parsed=$(split_response "$raw")
  local status body
  status=$(echo "$parsed" | sed -n '1p')
  body=$(echo "$parsed" | sed -n '2,$p')
  require_status "$status" "200" "login $username"
  local token
  token=$(json_extract "$body" "token")
  if [[ -z "$token" || "$token" == "null" ]]; then
    echo "Falha: token ausente no login de $username"
    echo "$body"
    exit 1
  fi
  echo "$token"
}

echo "[1/14] Login admin"
ADMIN_TOKEN=$(login "$ADMIN_USER" "$ADMIN_PASS")

SUFFIX=$(date +%s)
MUN_A="MunA_RBAC_$SUFFIX"
MUN_B="MunB_RBAC_$SUFFIX"
USER_PASS="Senha123"

echo "[2/14] Criando escolas base"
RAW=$(request POST "$API_BASE/schools" "$ADMIN_TOKEN" "{\"name\":\"Escola A RBAC $SUFFIX\",\"cnpj\":\"00.000.000/00$SUFFIX\",\"institution_type\":\"Municipal\",\"address\":{\"city\":\"$MUN_A\"}}")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
BODY=$(echo "$PARSED" | sed -n '2,$p')
require_status "$STATUS" "201" "create school A"
SCHOOL_A=$(json_extract "$BODY" "school.id")

RAW=$(request POST "$API_BASE/schools" "$ADMIN_TOKEN" "{\"name\":\"Escola B RBAC $SUFFIX\",\"cnpj\":\"11.111.111/11$SUFFIX\",\"institution_type\":\"Municipal\",\"address\":{\"city\":\"$MUN_B\"}}")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
BODY=$(echo "$PARSED" | sed -n '2,$p')
require_status "$STATUS" "201" "create school B"
SCHOOL_B=$(json_extract "$BODY" "school.id")

echo "[3/14] Criando professor e aluno de base"
RAW=$(request POST "$API_BASE/teachers" "$ADMIN_TOKEN" "{\"name\":\"Professor A $SUFFIX\",\"school_id\":\"$SCHOOL_A\",\"school_name\":\"Escola A RBAC $SUFFIX\",\"specialization\":\"AEE\"}")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
BODY=$(echo "$PARSED" | sed -n '2,$p')
require_status "$STATUS" "201" "create teacher A"
TEACHER_A=$(json_extract "$BODY" "teacher.id")

RAW=$(request POST "$API_BASE/students" "$ADMIN_TOKEN" "{\"name\":\"Aluno A $SUFFIX\",\"age\":\"10\",\"school_id\":\"$SCHOOL_A\",\"school_name\":\"Escola A RBAC $SUFFIX\",\"teacher_ids\":[\"$TEACHER_A\"],\"grade\":\"5\",\"class\":\"A\"}")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
BODY=$(echo "$PARSED" | sed -n '2,$p')
require_status "$STATUS" "201" "create student A"
STUDENT_A=$(json_extract "$BODY" "student.id")

echo "[4/14] Criando usuários dos 4 perfis operacionais"
create_user() {
  local username="$1"
  local role="$2"
  local municipio_id="$3"
  local school_id="$4"
  local teacher_id="$5"
  local payload
  payload="{\"username\":\"$username\",\"password\":\"$USER_PASS\",\"role\":\"$role\",\"municipio_id\":\"$municipio_id\",\"school_id\":\"$school_id\",\"teacher_id\":\"$teacher_id\"}"
  local raw parsed status
  raw=$(request POST "$API_BASE/auth/users" "$ADMIN_TOKEN" "$payload")
  parsed=$(split_response "$raw")
  status=$(echo "$parsed" | sed -n '1p')
  require_status "$status" "201" "create user $username/$role"
}

SEC_A="sec_a_$SUFFIX"
COORD_A="coord_a_$SUFFIX"
PROF_A="prof_a_$SUFFIX"
VIEW_SCHOOL_A="view_school_a_$SUFFIX"

create_user "$SEC_A" "secretaria" "$MUN_A" "" ""
create_user "$COORD_A" "coordenacao" "" "$SCHOOL_A" ""
create_user "$PROF_A" "professor" "" "$SCHOOL_A" "$TEACHER_A"
create_user "$VIEW_SCHOOL_A" "viewer" "" "$SCHOOL_A" ""

echo "[5/14] Login dos usuários"
TOKEN_SEC_A=$(login "$SEC_A" "$USER_PASS")
TOKEN_COORD_A=$(login "$COORD_A" "$USER_PASS")
TOKEN_PROF_A=$(login "$PROF_A" "$USER_PASS")
TOKEN_VIEW_A=$(login "$VIEW_SCHOOL_A" "$USER_PASS")

echo "[6/14] Garantindo que só admin cria usuário"
RAW=$(request POST "$API_BASE/auth/users" "$TOKEN_PROF_A" "{\"username\":\"x_${SUFFIX}\",\"password\":\"Senha123\",\"role\":\"viewer\",\"school_id\":\"$SCHOOL_A\"}")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
require_status "$STATUS" "403" "non-admin creating user"

echo "[7/14] Secretaria cria pré-cadastros"
RAW=$(request POST "$API_BASE/teachers" "$TOKEN_SEC_A" "{\"name\":\"Professor Sec $SUFFIX\",\"school_id\":\"$SCHOOL_A\",\"school_name\":\"Escola A RBAC $SUFFIX\",\"specialization\":\"AEE\"}")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
BODY=$(echo "$PARSED" | sed -n '2,$p')
require_status "$STATUS" "201" "secretaria creating teacher"
TEACHER_SEC=$(json_extract "$BODY" "teacher.id")

RAW=$(request POST "$API_BASE/students" "$TOKEN_SEC_A" "{\"name\":\"Aluno Sec $SUFFIX\",\"age\":\"9\",\"school_id\":\"$SCHOOL_A\",\"school_name\":\"Escola A RBAC $SUFFIX\",\"teacher_ids\":[\"$TEACHER_SEC\"],\"grade\":\"4\",\"class\":\"B\"}")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
require_status "$STATUS" "201" "secretaria creating student"

echo "[8/14] Coordenação não cria pré-cadastro e só vincula aluno-docente"
RAW=$(request POST "$API_BASE/teachers" "$TOKEN_COORD_A" "{\"name\":\"Professor Coord $SUFFIX\",\"school_id\":\"$SCHOOL_A\",\"school_name\":\"Escola A RBAC $SUFFIX\"}")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
require_status "$STATUS" "403" "coordenacao creating teacher"

RAW=$(request PUT "$API_BASE/students/$STUDENT_A" "$TOKEN_COORD_A" "{\"teacher_ids\":[\"$TEACHER_A\"]}")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
require_status "$STATUS" "200" "coordenacao linking student-teacher"

RAW=$(request PUT "$API_BASE/students/$STUDENT_A" "$TOKEN_COORD_A" "{\"grade\":\"6\"}")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
require_status "$STATUS" "403" "coordenacao editing non-link student fields"

echo "[9/14] Professor só edita Diário/PDI/Estudo de Caso"
RAW=$(request POST "$API_BASE/students" "$TOKEN_PROF_A" "{\"name\":\"Aluno Prof Bloq\",\"school_id\":\"$SCHOOL_A\",\"teacher_ids\":[\"$TEACHER_A\"]}")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
require_status "$STATUS" "403" "professor creating student"

RAW=$(request POST "$API_BASE/diary/entries" "$TOKEN_PROF_A" "{\"student_id\":\"$STUDENT_A\",\"student_name\":\"Aluno A $SUFFIX\",\"teachers\":[\"Professor A $SUFFIX\"],\"diary_date\":\"2026-04-26\",\"answers\":{\"lanchou\":\"Sim\"},\"open_obs\":\"ok\"}")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
BODY=$(echo "$PARSED" | sed -n '2,$p')
require_status "$STATUS" "201" "professor creating diary"
DIARY_ID=$(json_extract "$BODY" "entry.id")

RAW=$(request POST "$API_BASE/pdi" "$TOKEN_PROF_A" "{\"student_id\":\"$STUDENT_A\",\"student_name\":\"Aluno A $SUFFIX\",\"birth_date\":\"2015-01-01\",\"guardians\":[\"Responsável 1\"],\"diagnosis\":\"TEA\",\"class\":\"5A\",\"teachers\":[\"Professor A $SUFFIX\"],\"trimesters\":{\"trimester_1\":{},\"trimester_2\":{},\"trimester_3\":{}}}")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
require_status "$STATUS" "201" "professor creating pdi"

echo "[10/14] Viewer é somente leitura"
RAW=$(request GET "$API_BASE/students" "$TOKEN_VIEW_A")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
require_status "$STATUS" "200" "viewer reading students"

RAW=$(request POST "$API_BASE/diary/entries" "$TOKEN_VIEW_A" "{\"student_id\":\"$STUDENT_A\",\"student_name\":\"Aluno A $SUFFIX\",\"teachers\":[\"Professor A $SUFFIX\"],\"diary_date\":\"2026-04-26\",\"answers\":{\"lanchou\":\"Sim\"}}")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
require_status "$STATUS" "403" "viewer writing diary"

echo "[11/14] Escopo de leitura por perfil"
RAW=$(request GET "$API_BASE/schools/$SCHOOL_B" "$TOKEN_SEC_A")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
require_status "$STATUS" "403" "secretaria out-of-scope school"

RAW=$(request GET "$API_BASE/schools/$SCHOOL_B" "$TOKEN_COORD_A")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
require_status "$STATUS" "403" "coordenacao out-of-scope school"

RAW=$(request GET "$API_BASE/schools/$SCHOOL_A" "$TOKEN_VIEW_A")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
require_status "$STATUS" "200" "viewer in-scope school"

echo "[12/14] Limpeza de diário/PDI"
if [[ -n "$DIARY_ID" && "$DIARY_ID" != "null" ]]; then
  RAW=$(request DELETE "$API_BASE/diary/entries/$DIARY_ID" "$ADMIN_TOKEN")
  PARSED=$(split_response "$RAW")
  STATUS=$(echo "$PARSED" | sed -n '1p')
  require_status "$STATUS" "200" "cleanup diary"
fi

# Remove PDI criado para o aluno base (pega o atual por estudante)
RAW=$(request GET "$API_BASE/pdi/Aluno%20A%20$SUFFIX?student_id=$STUDENT_A" "$ADMIN_TOKEN")
PARSED=$(split_response "$RAW")
STATUS=$(echo "$PARSED" | sed -n '1p')
if [[ "$STATUS" == "200" ]]; then
  BODY=$(echo "$PARSED" | sed -n '2,$p')
  PDI_ID=$(json_extract "$BODY" "id")
  if [[ -n "$PDI_ID" && "$PDI_ID" != "null" ]]; then
    RAW=$(request DELETE "$API_BASE/pdi/$PDI_ID" "$ADMIN_TOKEN")
    PARSED=$(split_response "$RAW")
    STATUS=$(echo "$PARSED" | sed -n '1p')
    require_status "$STATUS" "200" "cleanup pdi"
  fi
fi

echo "[13/14] Limpeza de alunos/docentes/escolas"
request DELETE "$API_BASE/students/$STUDENT_A" "$ADMIN_TOKEN" >/dev/null
request DELETE "$API_BASE/teachers/$TEACHER_A" "$ADMIN_TOKEN" >/dev/null
if [[ -n "${TEACHER_SEC:-}" ]]; then
  request DELETE "$API_BASE/teachers/$TEACHER_SEC" "$ADMIN_TOKEN" >/dev/null
fi
request DELETE "$API_BASE/schools/$SCHOOL_A" "$ADMIN_TOKEN" >/dev/null
request DELETE "$API_BASE/schools/$SCHOOL_B" "$ADMIN_TOKEN" >/dev/null

echo "[14/14] Smoke RBAC de perfis concluído com sucesso"
echo "Nota: usuários criados para teste não são removidos automaticamente."
