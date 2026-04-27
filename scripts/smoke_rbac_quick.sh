#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:5000/api}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-admin123}"

jget() {
  local path="$1"
  python3 -c 'import json,sys
path=sys.argv[1].split(".")
obj=json.load(sys.stdin)
cur=obj
for p in path:
  if isinstance(cur, dict):
    cur=cur.get(p)
  else:
    cur=None
    break
print("" if cur is None else cur)
' "$path"
}

login_token() {
  local user="$1"
  local pass="$2"
  curl -sS --connect-timeout 5 --max-time 15 -X POST "$API_BASE/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$user\",\"password\":\"$pass\"}" | jget token
}

http_code() {
  local method="$1"
  local path="$2"
  local token="$3"
  local body="${4:-}"
  local url="$API_BASE$path"
  local args=(curl -sS --connect-timeout 5 --max-time 15 -o /tmp/rbac_quick_out.json -w '%{http_code}' -X "$method" "$url" -H 'Content-Type: application/json')
  if [[ -n "$token" ]]; then
    args+=(-H "Authorization: Bearer $token")
  fi
  if [[ -n "$body" ]]; then
    args+=(-d "$body")
  fi
  "${args[@]}"
}

expect_code() {
  local got="$1"
  local want="$2"
  local label="$3"
  if [[ "$got" == "$want" ]]; then
    echo "PASS: $label ($got)"
  else
    echo "FAIL: $label (esperado=$want, obtido=$got)"
    [[ -f /tmp/rbac_quick_out.json ]] && cat /tmp/rbac_quick_out.json
    exit 1
  fi
}

echo "[1] Login admin"
ADMIN_TOKEN=$(login_token "$ADMIN_USER" "$ADMIN_PASS")
[[ -n "$ADMIN_TOKEN" ]] || { echo "FAIL: login admin"; exit 1; }

SUFFIX=$(date +%s)
MUN="RBAC_MUN_$SUFFIX"

echo "[2] Seed escola/docente/aluno"
CODE=$(http_code POST "/schools" "$ADMIN_TOKEN" "{\"name\":\"RBAC Escola $SUFFIX\",\"cnpj\":\"00.000.000/$SUFFIX\",\"institution_type\":\"Municipal\",\"address\":{\"city\":\"$MUN\"}}")
expect_code "$CODE" "201" "admin cria escola"
SCHOOL_ID=$(cat /tmp/rbac_quick_out.json | jget school.id)

CODE=$(http_code POST "/teachers" "$ADMIN_TOKEN" "{\"name\":\"RBAC Prof $SUFFIX\",\"school_id\":\"$SCHOOL_ID\",\"school_name\":\"RBAC Escola $SUFFIX\",\"specialization\":\"AEE\"}")
expect_code "$CODE" "201" "admin cria docente"
TEACHER_ID=$(cat /tmp/rbac_quick_out.json | jget teacher.id)

CODE=$(http_code POST "/students" "$ADMIN_TOKEN" "{\"name\":\"RBAC Aluno $SUFFIX\",\"age\":\"10\",\"school_id\":\"$SCHOOL_ID\",\"school_name\":\"RBAC Escola $SUFFIX\",\"teacher_ids\":[\"$TEACHER_ID\"]}")
expect_code "$CODE" "201" "admin cria aluno"
STUDENT_ID=$(cat /tmp/rbac_quick_out.json | jget student.id)

echo "[3] Cria usuários por perfil"
create_user() {
  local username="$1"
  local role="$2"
  local municipio_id="$3"
  local school_id="$4"
  local teacher_id="$5"
  local payload="{\"username\":\"$username\",\"password\":\"Senha123\",\"role\":\"$role\",\"municipio_id\":\"$municipio_id\",\"school_id\":\"$school_id\",\"teacher_id\":\"$teacher_id\"}"
  local code
  code=$(http_code POST "/auth/users" "$ADMIN_TOKEN" "$payload")
  expect_code "$code" "201" "admin cria usuário $role"
}

SEC_USER="rbac_sec_$SUFFIX"
COORD_USER="rbac_coord_$SUFFIX"
PROF_USER="rbac_prof_$SUFFIX"
VIEW_USER="rbac_view_$SUFFIX"

create_user "$SEC_USER" "secretaria" "$MUN" "" ""
create_user "$COORD_USER" "coordenacao" "" "$SCHOOL_ID" ""
create_user "$PROF_USER" "professor" "" "$SCHOOL_ID" "$TEACHER_ID"
create_user "$VIEW_USER" "viewer" "" "$SCHOOL_ID" ""

SEC_TOKEN=$(login_token "$SEC_USER" "Senha123")
COORD_TOKEN=$(login_token "$COORD_USER" "Senha123")
PROF_TOKEN=$(login_token "$PROF_USER" "Senha123")
VIEW_TOKEN=$(login_token "$VIEW_USER" "Senha123")

[[ -n "$SEC_TOKEN" && -n "$COORD_TOKEN" && -n "$PROF_TOKEN" && -n "$VIEW_TOKEN" ]] || { echo "FAIL: login perfis"; exit 1; }

echo "[4] Regras críticas"
CODE=$(http_code POST "/auth/users" "$PROF_TOKEN" "{\"username\":\"deny_$SUFFIX\",\"password\":\"Senha123\",\"role\":\"viewer\",\"school_id\":\"$SCHOOL_ID\"}")
expect_code "$CODE" "403" "só admin cria usuário"

CODE=$(http_code POST "/teachers" "$COORD_TOKEN" "{\"name\":\"Coord Nao Deve\",\"school_id\":\"$SCHOOL_ID\",\"school_name\":\"RBAC Escola $SUFFIX\"}")
expect_code "$CODE" "403" "coordenação não cria docente"

CODE=$(http_code PUT "/students/$STUDENT_ID" "$COORD_TOKEN" "{\"teacher_ids\":[\"$TEACHER_ID\"]}")
expect_code "$CODE" "200" "coordenação vincula aluno-docente"

CODE=$(http_code PUT "/students/$STUDENT_ID" "$COORD_TOKEN" "{\"grade\":\"6\"}")
expect_code "$CODE" "403" "coordenação não edita outros campos do aluno"

CODE=$(http_code POST "/diary/entries" "$PROF_TOKEN" "{\"student_id\":\"$STUDENT_ID\",\"student_name\":\"RBAC Aluno $SUFFIX\",\"teachers\":[\"RBAC Prof $SUFFIX\"],\"diary_date\":\"2026-04-26\",\"answers\":{\"lanchou\":\"Sim\"}}")
expect_code "$CODE" "201" "professor cria diário"

CODE=$(http_code POST "/diary/entries" "$VIEW_TOKEN" "{\"student_id\":\"$STUDENT_ID\",\"student_name\":\"RBAC Aluno $SUFFIX\",\"teachers\":[\"RBAC Prof $SUFFIX\"],\"diary_date\":\"2026-04-26\",\"answers\":{\"lanchou\":\"Sim\"}}")
expect_code "$CODE" "403" "viewer não cria diário"

CODE=$(http_code GET "/students" "$VIEW_TOKEN")
expect_code "$CODE" "200" "viewer consulta alunos"

echo "[5] Limpeza mínima"
http_code DELETE "/students/$STUDENT_ID" "$ADMIN_TOKEN" >/dev/null || true
http_code DELETE "/teachers/$TEACHER_ID" "$ADMIN_TOKEN" >/dev/null || true
http_code DELETE "/schools/$SCHOOL_ID" "$ADMIN_TOKEN" >/dev/null || true

echo "SMOKE RBAC QUICK CONCLUIDO"
