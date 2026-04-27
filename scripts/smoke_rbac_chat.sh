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

http_post() {
  local url="$1"
  local token="$2"
  local body="$3"
  if [[ -n "$token" ]]; then
    curl -s -X POST "$url" -H "Authorization: Bearer $token" -H "Content-Type: application/json" -d "$body"
  else
    curl -s -X POST "$url" -H "Content-Type: application/json" -d "$body"
  fi
}

echo "[1/12] Login admin"
LOGIN_RESP=$(http_post "$API_BASE/auth/login" "" "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}")
ADMIN_TOKEN=$(json_extract "$LOGIN_RESP" "token")
if [[ -z "$ADMIN_TOKEN" || "$ADMIN_TOKEN" == "null" ]]; then
  echo "Falha no login admin"
  echo "$LOGIN_RESP"
  exit 1
fi

SUFFIX=$(date +%s)
MUNICIPIO_OK="CidadeTesteRBAC"
MUNICIPIO_DENY="CidadeSemAcesso"

SECRETARIA_OK_USER="sec_ok_$SUFFIX"
SECRETARIA_DENY_USER="sec_no_$SUFFIX"
COORD_USER="coord_$SUFFIX"
PROF_USER="prof_$SUFFIX"
PROF_DENY_USER="prof_no_$SUFFIX"
USER_PASS="Senha123"

echo "[2/12] Criando escola e aluno base"
SCHOOL_RESP=$(http_post "$API_BASE/schools" "$ADMIN_TOKEN" '{
  "name":"Escola RBAC Chat",
  "cnpj":"00.000.000/0099-00",
  "institution_type":"Municipal",
  "address":{"city":"'"$MUNICIPIO_OK"'"}
}')
SCHOOL_ID=$(json_extract "$SCHOOL_RESP" "school.id")
if [[ -z "$SCHOOL_ID" || "$SCHOOL_ID" == "null" ]]; then
  echo "Falha ao criar escola"
  echo "$SCHOOL_RESP"
  exit 1
fi

STUDENT_RESP=$(http_post "$API_BASE/students" "$ADMIN_TOKEN" "{
  \"name\":\"Aluno RBAC Chat\",
  \"age\":\"10\",
  \"school_id\":\"$SCHOOL_ID\",
  \"school_name\":\"Escola RBAC Chat\",
  \"grade\":\"5\",
  \"class\":\"A\"
}")
STUDENT_ID=$(json_extract "$STUDENT_RESP" "student.id")
if [[ -z "$STUDENT_ID" || "$STUDENT_ID" == "null" ]]; then
  echo "Falha ao criar aluno"
  echo "$STUDENT_RESP"
  exit 1
fi

echo "[3/12] Criando usuários por papel (somente admin)"
create_user_payload() {
  local username="$1"
  local role="$2"
  local municipio_id="$3"
  local school_id="$4"
  cat <<EOF
{"username":"$username","password":"$USER_PASS","role":"$role","municipio_id":"$municipio_id","school_id":"$school_id"}
EOF
}

for spec in \
  "$SECRETARIA_OK_USER secretaria $MUNICIPIO_OK " \
  "$SECRETARIA_DENY_USER secretaria $MUNICIPIO_DENY " \
  "$COORD_USER coordenacao  $SCHOOL_ID" \
  "$PROF_USER professor  $SCHOOL_ID" \
  "$PROF_DENY_USER professor  other-school"; do
  username=$(echo "$spec" | awk '{print $1}')
  role=$(echo "$spec" | awk '{print $2}')
  municipio_id=$(echo "$spec" | awk '{print $3}')
  school_id=$(echo "$spec" | awk '{print $4}')
  RESP=$(http_post "$API_BASE/auth/users" "$ADMIN_TOKEN" "$(create_user_payload "$username" "$role" "$municipio_id" "$school_id")")
  CREATED_ID=$(json_extract "$RESP" "user.id")
  if [[ -z "$CREATED_ID" || "$CREATED_ID" == "null" ]]; then
    echo "Falha ao criar usuário $username"
    echo "$RESP"
    exit 1
  fi
done

echo "[4/12] Login dos usuários de teste"
login_user() {
  local username="$1"
  local resp
  resp=$(http_post "$API_BASE/auth/login" "" "{\"username\":\"$username\",\"password\":\"$USER_PASS\"}")
  json_extract "$resp" "token"
}

TOKEN_SEC_OK=$(login_user "$SECRETARIA_OK_USER")
TOKEN_SEC_DENY=$(login_user "$SECRETARIA_DENY_USER")
TOKEN_COORD=$(login_user "$COORD_USER")
TOKEN_PROF=$(login_user "$PROF_USER")
TOKEN_PROF_DENY=$(login_user "$PROF_DENY_USER")

for token_name in TOKEN_SEC_OK TOKEN_SEC_DENY TOKEN_COORD TOKEN_PROF TOKEN_PROF_DENY; do
  token_value="${!token_name}"
  if [[ -z "$token_value" || "$token_value" == "null" ]]; then
    echo "Falha de login para $token_name"
    exit 1
  fi
done

echo "[5/12] Professor cria conversa no chat (persiste sessão/mensagens)"
CHAT_RESP=$(http_post "$API_BASE/rag/chat" "$TOKEN_PROF" "{
  \"message\":\"Teste de persistencia de chat\",
  \"student_id\":\"$STUDENT_ID\",
  \"student_name\":\"Aluno RBAC Chat\",
  \"school_id\":\"$SCHOOL_ID\",
  \"school\":\"Escola RBAC Chat\",
  \"selected_sources\":{\"vector_documents\":false,\"diary\":false,\"pdi\":false,\"student_pre_registration\":true,\"teachers_pre_registration\":false,\"school_pre_registration\":true,\"linked_peis\":false}
}")

if [[ -n "$(json_extract "$CHAT_RESP" "error")" ]]; then
  echo "Falha no /api/rag/chat"
  echo "$CHAT_RESP"
  echo "Obs: esse teste exige GOOGLE_API_KEY e PostgreSQL/Supabase ativos."
  exit 1
fi

SESSION_ID=$(json_extract "$CHAT_RESP" "session_id")
if [[ -z "$SESSION_ID" || "$SESSION_ID" == "null" ]]; then
  echo "Sessão não retornada no chat"
  echo "$CHAT_RESP"
  exit 1
fi

echo "[6/12] Verificando visibilidade de sessões por papel"
get_sessions_count() {
  local token="$1"
  local resp
  resp=$(curl -s "$API_BASE/rag/chat/sessions?student_id=$STUDENT_ID" -H "Authorization: Bearer $token")
  json_extract "$resp" "count"
}

COUNT_PROF=$(get_sessions_count "$TOKEN_PROF")
COUNT_COORD=$(get_sessions_count "$TOKEN_COORD")
COUNT_SEC_OK=$(get_sessions_count "$TOKEN_SEC_OK")
COUNT_SEC_DENY=$(get_sessions_count "$TOKEN_SEC_DENY")
COUNT_PROF_DENY=$(get_sessions_count "$TOKEN_PROF_DENY")

echo "professor dono: $COUNT_PROF"
echo "coord escola:   $COUNT_COORD"
echo "secretaria ok:  $COUNT_SEC_OK"
echo "secretaria no:  $COUNT_SEC_DENY"
echo "prof sem escopo:$COUNT_PROF_DENY"

if [[ "$COUNT_PROF" == "0" || "$COUNT_COORD" == "0" || "$COUNT_SEC_OK" == "0" ]]; then
  echo "Falha: papéis com acesso esperado não visualizaram sessão"
  exit 1
fi

if [[ "$COUNT_SEC_DENY" != "0" || "$COUNT_PROF_DENY" != "0" ]]; then
  echo "Falha: papéis sem escopo visualizaram sessão"
  exit 1
fi

echo "[7/12] Validando leitura de mensagens da sessão"
MSG_OK=$(curl -s "$API_BASE/rag/chat/sessions/$SESSION_ID/messages" -H "Authorization: Bearer $TOKEN_COORD")
if [[ "$(json_extract "$MSG_OK" "count")" == "0" ]]; then
  echo "Falha: coordenação não conseguiu ler mensagens"
  echo "$MSG_OK"
  exit 1
fi

MSG_DENY=$(curl -s "$API_BASE/rag/chat/sessions/$SESSION_ID/messages" -H "Authorization: Bearer $TOKEN_SEC_DENY")
if [[ "$(json_extract "$MSG_DENY" "error")" == "" ]]; then
  echo "Falha: secretaria sem escopo conseguiu ler sessão"
  echo "$MSG_DENY"
  exit 1
fi

echo "[8/12] Validando agrupamento por dia"
BY_DAY=$(curl -s "$API_BASE/rag/chat/history-by-day?student_id=$STUDENT_ID" -H "Authorization: Bearer $TOKEN_SEC_OK")
if [[ "$(json_extract "$BY_DAY" "count")" == "0" ]]; then
  echo "Falha: histórico por dia não retornou dados"
  echo "$BY_DAY"
  exit 1
fi

echo "[9/12] Verificando que apenas admin cria usuário"
NEG_CREATE=$(http_post "$API_BASE/auth/users" "$TOKEN_PROF" '{"username":"forbidden_user","password":"Senha123","role":"professor","school_id":"x"}')
if [[ "$(json_extract "$NEG_CREATE" "error")" == "" ]]; then
  echo "Falha: professor conseguiu criar usuário"
  echo "$NEG_CREATE"
  exit 1
fi

echo "[10/12] Limpando aluno e escola de teste"
curl -s -X DELETE "$API_BASE/students/$STUDENT_ID" -H "Authorization: Bearer $ADMIN_TOKEN" >/dev/null
curl -s -X DELETE "$API_BASE/schools/$SCHOOL_ID" -H "Authorization: Bearer $ADMIN_TOKEN" >/dev/null

echo "[11/12] Observação importante"
echo "Usuários de teste não são removidos automaticamente (não há endpoint de delete user)."

echo "[12/12] Smoke RBAC + Chat concluído com sucesso"
