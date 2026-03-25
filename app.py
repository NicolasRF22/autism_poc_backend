import os
import copy
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, send_file, g
from flask_cors import CORS
from dotenv import load_dotenv
import json
from typing import Dict, List
import orjson
import jwt
from werkzeug.utils import secure_filename

load_dotenv()


def _to_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _parse_cors_origins() -> list:
    raw = os.getenv('CORS_ALLOWED_ORIGINS', '*').strip()
    if not raw:
        return ['*']
    if raw == '*':
        return ['*']
    return [origin.strip() for origin in raw.split(',') if origin.strip()]

app = Flask(__name__)
DEBUG_MODE = _to_bool(os.getenv('DEBUG', 'False'), default=False)
CORS(app, resources={r'/api/*': {'origins': _parse_cors_origins()}})

# ------------------------------------------------------------------
# RAG Engine (inicializado sob demanda para evitar falha sem API key)
# ------------------------------------------------------------------
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
PEIS_FOLDER = os.path.join(os.path.dirname(__file__), 'peis')
DIARIES_FOLDER = os.path.join(os.path.dirname(__file__), 'diaries')
PDIS_FOLDER = os.path.join(os.path.dirname(__file__), 'pdis')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PEIS_FOLDER, exist_ok=True)
os.makedirs(DIARIES_FOLDER, exist_ok=True)
os.makedirs(PDIS_FOLDER, exist_ok=True)

from pei_storage import PEIStorage
from diary_storage import DiaryStorage
from pdi_storage import PDIStorage
from school_storage import SchoolStorage
from student_storage import StudentStorage
from teacher_storage import TeacherStorage
from auth_storage import AuthStorage, VALID_ROLES
from audit_storage import AuditStorage
from diary_pdf_parser import parse_diary_pdf, QUESTION_PATTERNS
from usage_tracker import get_usage_snapshot
_pei_storage = PEIStorage(storage_dir=PEIS_FOLDER)
_diary_storage = DiaryStorage(storage_dir=DIARIES_FOLDER)
_pdi_storage = PDIStorage(storage_dir=PDIS_FOLDER)

SCHOOLS_FOLDER = os.path.join(os.path.dirname(__file__), 'schools')
STUDENTS_FOLDER = os.path.join(os.path.dirname(__file__), 'students')
USERS_FOLDER = os.path.join(os.path.dirname(__file__), 'users')
AUDIT_FOLDER = os.path.join(os.path.dirname(__file__), 'audit_logs')
TEACHERS_FOLDER = os.path.join(os.path.dirname(__file__), 'teachers')
os.makedirs(SCHOOLS_FOLDER, exist_ok=True)
os.makedirs(STUDENTS_FOLDER, exist_ok=True)
os.makedirs(USERS_FOLDER, exist_ok=True)
os.makedirs(AUDIT_FOLDER, exist_ok=True)
os.makedirs(TEACHERS_FOLDER, exist_ok=True)
_school_storage = SchoolStorage(storage_dir=SCHOOLS_FOLDER)
_student_storage = StudentStorage(storage_dir=STUDENTS_FOLDER)
_teacher_storage = TeacherStorage(storage_dir=TEACHERS_FOLDER)
_auth_storage = AuthStorage(
    storage_dir=USERS_FOLDER,
    default_admin_username=os.getenv('AUTH_ADMIN_USERNAME', 'admin'),
    default_admin_password=os.getenv('AUTH_ADMIN_PASSWORD', ''),
)
_audit_storage = AuditStorage(storage_dir=AUDIT_FOLDER)

JWT_SECRET = os.getenv('AUTH_JWT_SECRET') or os.getenv('SECRET_KEY')
if not JWT_SECRET:
    if DEBUG_MODE:
        JWT_SECRET = 'dev-only-jwt-secret'
    else:
        raise RuntimeError('AUTH_JWT_SECRET não configurado. Defina no .env para iniciar em produção.')
JWT_ALGORITHM = 'HS256'
JWT_EXP_MINUTES = int(os.getenv('AUTH_TOKEN_EXP_MINUTES', '480'))

PUBLIC_API_PATHS = {
    '/api/health',
    '/api/auth/login',
}

ADMIN_ONLY_PREFIXES = (
    '/api/auth/users',
    '/api/audit',
    '/api/teachers',
    '/api/admin',
)

MUTATING_METHODS = {'POST', 'PUT', 'DELETE', 'PATCH'}

_rag_engine = None

def get_rag_engine():
    global _rag_engine
    if _rag_engine is None:
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            return None
        from rag_engine import RAGEngine
        _rag_engine = RAGEngine(api_key=api_key)
    return _rag_engine


def _extract_bearer_token() -> str:
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return ''
    return auth_header.replace('Bearer ', '', 1).strip()


def _build_token(user: Dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        'sub': user['id'],
        'username': user['username'],
        'role': user['role'],
        'iat': now,
        'exp': now + timedelta(minutes=JWT_EXP_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> Dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def _sanitize_current_user(user: Dict) -> Dict:
    return {
        'id': user['id'],
        'username': user['username'],
        'role': user['role'],
    }


def _is_admin_only_path(path: str) -> bool:
    return path.startswith(ADMIN_ONLY_PREFIXES)


def _should_audit_request(path: str, method: str) -> bool:
    if method == 'OPTIONS':
        return False
    if path in PUBLIC_API_PATHS:
        return False
    if path.startswith('/api/auth/logout'):
        return False
    if method in MUTATING_METHODS:
        return True
    if 'download' in path or path.endswith('/pdf'):
        return True
    return False


@app.before_request
def enforce_auth_and_permissions():
    if not request.path.startswith('/api'):
        return None

    if request.method == 'OPTIONS':
        return None

    g.current_user = None
    if request.path in PUBLIC_API_PATHS:
        return None

    token = _extract_bearer_token()
    if not token:
        return jsonify({'error': 'Token de autenticação ausente'}), 401

    try:
        payload = _decode_token(token)
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Sessão expirada. Faça login novamente'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Token inválido'}), 401

    user = _auth_storage.get_user_by_id(payload.get('sub', ''))
    if not user or not user.get('is_active', True):
        return jsonify({'error': 'Usuário inválido ou inativo'}), 401

    g.current_user = _sanitize_current_user(user)

    if _is_admin_only_path(request.path) and g.current_user['role'] != 'admin':
        return jsonify({'error': 'Acesso negado para este perfil'}), 403

    if request.method in MUTATING_METHODS and g.current_user['role'] == 'viewer':
        return jsonify({'error': 'Perfil viewer possui apenas leitura'}), 403

    return None


@app.after_request
def audit_api_requests(response):
    if request.path.startswith('/api') and _should_audit_request(request.path, request.method):
        _audit_storage.log_event(
            action=f'{request.method} {request.path}',
            status_code=response.status_code,
            path=request.path,
            method=request.method,
            user=getattr(g, 'current_user', None),
        )
    return response

# Armazenamento em memória (pode ser substituído por banco de dados)
submissions = []

# Definição dos formulários disponíveis
FORMS = {
    "cadastro_escola": {
        "id": "cadastro_escola",
        "name": "Cadastro da Escola",
        "description": "Formulário para cadastro de instituições educacionais que oferecem atendimento a estudantes com TEA",
        "sections": 8
    },
    "cadastro_aluno": {
        "id": "cadastro_aluno",
        "name": "Cadastro do Aluno",
        "description": "Formulário para cadastro detalhado de alunos com TEA, incluindo informações pessoais, escolares e familiares",
        "sections": 6
    }
}

@app.route('/api/forms', methods=['GET'])
def get_forms():
    """Retorna lista de formulários disponíveis"""
    forms_list = [
        {
            "id": form["id"],
            "name": form["name"],
            "description": form["description"]
        }
        for form in FORMS.values()
    ]
    return jsonify(forms_list)

@app.route('/api/forms/<form_id>', methods=['GET'])
def get_form(form_id):
    """Retorna um formulário específico"""
    form = FORMS.get(form_id)
    if not form:
        return jsonify({"error": "Formulário não encontrado"}), 404
    return jsonify(form)

@app.route('/api/submissions', methods=['POST'])
def submit_form():
    """Submete um formulário preenchido"""
    data = request.json
    
    if not data or 'form_id' not in data or 'answers' not in data:
        return jsonify({"error": "Dados inválidos"}), 400
    
    submission = {
        "id": len(submissions) + 1,
        "form_id": data['form_id'],
        "form_name": FORMS.get(data['form_id'], {}).get('name', 'Desconhecido'),
        "answers": data['answers'],
        "submitted_at": datetime.now().isoformat(),
        "metadata": data.get('metadata', {})
    }
    
    submissions.append(submission)
    
    return jsonify({
        "message": "Formulário submetido com sucesso",
        "submission_id": submission['id']
    }), 201

@app.route('/api/submissions', methods=['GET'])
def get_submissions():
    """Retorna todas as submissões"""
    return jsonify(submissions)

@app.route('/api/submissions/<int:submission_id>', methods=['GET'])
def get_submission(submission_id):
    """Retorna uma submissão específica"""
    submission = next((s for s in submissions if s['id'] == submission_id), None)
    if not submission:
        return jsonify({"error": "Submissão não encontrada"}), 404
    return jsonify(submission)

@app.route('/api/submissions/<int:submission_id>/download', methods=['GET'])
def download_submission(submission_id):
    """Baixa uma submissão em formato JSON"""
    submission = next((s for s in submissions if s['id'] == submission_id), None)
    if not submission:
        return jsonify({"error": "Submissão não encontrada"}), 404
    
    # Cria arquivo JSON temporário
    filename = f"submission_{submission_id}_{submission['form_id']}.json"
    filepath = f"/tmp/{filename}"
    
    with open(filepath, 'wb') as f:
        f.write(orjson.dumps(submission, option=orjson.OPT_INDENT_2))
    
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/api/submissions/download-all', methods=['GET'])
def download_all_submissions():
    """Baixa todas as submissões em formato JSON"""
    if not submissions:
        return jsonify({"error": "Nenhuma submissão encontrada"}), 404
    
    filename = f"all_submissions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = f"/tmp/{filename}"
    
    with open(filepath, 'wb') as f:
        f.write(orjson.dumps(submissions, option=orjson.OPT_INDENT_2))
    
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/api/health', methods=['GET'])
def health():
    """Verifica o status da API"""
    return jsonify({"status": "ok", "message": "Autism.IA API is running"})


# ==================================================================
# AUTH ROUTES
# ==================================================================

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """Autentica usuário e retorna JWT."""
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'error': 'Usuário e senha são obrigatórios'}), 400

    user = _auth_storage.authenticate(username=username, password=password)
    if not user:
        _audit_storage.log_event(
            action='LOGIN',
            status_code=401,
            path=request.path,
            method=request.method,
            details={'username': username},
        )
        return jsonify({'error': 'Credenciais inválidas'}), 401

    token = _build_token(user)
    safe_user = _sanitize_current_user(user)

    _audit_storage.log_event(
        action='LOGIN',
        status_code=200,
        path=request.path,
        method=request.method,
        user=safe_user,
    )

    return jsonify(
        {
            'token': token,
            'expires_in_minutes': JWT_EXP_MINUTES,
            'user': safe_user,
        }
    )


@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    """Retorna usuário autenticado atual."""
    return jsonify({'user': g.current_user})


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """Logout stateless (cliente deve descartar o token)."""
    _audit_storage.log_event(
        action='LOGOUT',
        status_code=200,
        path=request.path,
        method=request.method,
        user=g.current_user,
    )
    return jsonify({'message': 'Logout realizado com sucesso'})


@app.route('/api/auth/users', methods=['GET'])
def list_users():
    """Lista usuários cadastrados (admin)."""
    return jsonify(_auth_storage.list_users())


@app.route('/api/auth/users', methods=['POST'])
def create_user():
    """Cria novo usuário (admin)."""
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    role = (data.get('role') or '').strip().lower()

    if role not in VALID_ROLES:
        return jsonify({'error': 'Perfil inválido. Use admin, editor ou viewer'}), 400

    try:
        user = _auth_storage.create_user(username=username, password=password, role=role)
        return jsonify({'message': 'Usuário criado com sucesso', 'user': user}), 201
    except ValueError as err:
        return jsonify({'error': str(err)}), 400


@app.route('/api/auth/users/<user_id>/role', methods=['PUT'])
def update_user_role(user_id):
    """Atualiza perfil de usuário (admin)."""
    data = request.json or {}
    role = (data.get('role') or '').strip().lower()

    if role not in VALID_ROLES:
        return jsonify({'error': 'Perfil inválido. Use admin, editor ou viewer'}), 400

    try:
        user = _auth_storage.update_user_role(user_id=user_id, role=role)
        if not user:
            return jsonify({'error': 'Usuário não encontrado'}), 404
        return jsonify({'message': 'Perfil atualizado com sucesso', 'user': user})
    except ValueError as err:
        return jsonify({'error': str(err)}), 400


# ==================================================================
# AUDIT ROUTES
# ==================================================================

@app.route('/api/audit/events', methods=['GET'])
def get_audit_events():
    """Lista eventos de auditoria (admin)."""
    limit_raw = request.args.get('limit', '200')
    try:
        limit = int(limit_raw)
    except ValueError:
        return jsonify({'error': 'Parâmetro limit inválido'}), 400

    events = _audit_storage.list_events(limit=limit)
    return jsonify(events)


@app.route('/api/admin/model-usage', methods=['GET'])
def get_model_usage():
    """Retorna uso atual e limites configurados por modelo (admin)."""
    additional_models = [
        os.getenv('GOOGLE_GENERATION_MODEL', 'gemini-2.5-flash'),
        os.getenv('GOOGLE_EMBEDDING_MODEL', 'gemini-embedding-001'),
    ]
    payload = get_usage_snapshot(additional_models=additional_models)
    return jsonify(payload)


# ==================================================================
# DIARY ROUTES
# ==================================================================

@app.route('/api/diary/students', methods=['GET'])
def get_diary_students():
    """Lista todos os alunos com diários (com resumos)"""
    try:
        summaries = _diary_storage.list_all_summaries()
        return jsonify(summaries)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/diary/entries/<student_name>', methods=['GET'])
def get_student_entries(student_name):
    """Retorna todas as entradas de diário de um aluno específico"""
    try:
        entries = _diary_storage.get_entries_by_student(student_name)
        return jsonify(entries)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/diary/entries', methods=['POST'])
def create_diary_entry():
    """Cria uma nova entrada de diário"""
    data = request.json or {}
    
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400
    
    required_fields = ['student_name', 'teachers', 'diary_date', 'answers']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Campo obrigatório ausente: {field}"}), 400
    
    try:
        student_id = (data.get('student_id') or '').strip() or None
        status = (data.get('status') or 'final').strip().lower()
        source = (data.get('source') or 'manual').strip().lower()
        parse_warnings = data.get('parse_warnings') or []

        if status not in {'draft', 'final'}:
            return jsonify({"error": "Status inválido. Use draft ou final"}), 400

        if not isinstance(parse_warnings, list):
            return jsonify({"error": "parse_warnings deve ser uma lista"}), 400

        warnings = copy.deepcopy(parse_warnings)
        if _diary_storage.has_date_conflict(student_id, data['student_name'], data['diary_date']):
            warnings.append('Já existe registro para o mesmo aluno e data')

        entry = _diary_storage.save_entry(
            student_name=data['student_name'],
            teachers=data['teachers'],
            diary_date=data['diary_date'],
            answers=data['answers'],
            open_obs=data.get('open_obs', ''),
            student_id=student_id,
            status=status,
            source=source,
            parse_warnings=warnings,
        )
        return jsonify({
            "message": "Entrada de diário criada com sucesso",
            "entry": entry
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/diary/entries/<entry_id>', methods=['GET'])
def get_diary_entry(entry_id):
    """Retorna uma entrada específica de diário"""
    try:
        entry = _diary_storage.get_entry(entry_id)
        if not entry:
            return jsonify({"error": "Entrada não encontrada"}), 404
        return jsonify(entry)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/diary/entries/<entry_id>', methods=['DELETE'])
def delete_diary_entry(entry_id):
    """Remove uma entrada de diário"""
    try:
        if _diary_storage.delete_entry(entry_id):
            return jsonify({"message": "Entrada removida com sucesso"})
        return jsonify({"error": "Entrada não encontrada"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/diary/last-teachers/<student_name>', methods=['GET'])
def get_last_teachers(student_name):
    """Retorna os professores da última entrada de um aluno (para usar como padrão)"""
    try:
        teachers = _diary_storage.get_last_teachers(student_name)
        return jsonify({"teachers": teachers})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _resolve_student(student_id: str, student_name: str):
    if student_id:
        student = _student_storage.get_student(student_id)
        if student:
            resolved_name = student.get('name') or student.get('studentName') or student_name
            return student.get('id'), resolved_name, []
        return None, student_name, ['student_id informado não foi encontrado']

    if student_name:
        matches = _student_storage.find_students_by_name(student_name)
        if len(matches) == 1:
            match = matches[0]
            resolved_name = match.get('name') or match.get('studentName') or student_name
            return match.get('id'), resolved_name, []
        if len(matches) > 1:
            return None, student_name, ['Nome do aluno ambíguo. Selecione manualmente no preview']
        return None, student_name, ['Aluno não encontrado no cadastro']

    return None, '', ['Aluno não identificado no PDF']


def _validate_commit_entry(entry: Dict):
    status = (entry.get('status') or 'draft').strip().lower()
    if status not in {'draft', 'final'}:
        return False, 'Status inválido. Use draft ou final'

    if status == 'final':
        if not entry.get('diary_date'):
            return False, 'Entrada final exige diary_date'
        if not entry.get('teachers'):
            return False, 'Entrada final exige ao menos um professor'

    return True, ''


@app.route('/api/diary/import/preview', methods=['POST'])
def preview_diary_import():
    """Gera preview de importação de diário a partir de PDF, sem persistir."""
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400

    file = request.files['file']
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Apenas arquivos PDF são permitidos'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        preferred_student_id = (request.form.get('student_id') or '').strip()
        preferred_student_name = (request.form.get('student_name') or '').strip()
        use_ocr_raw = (request.form.get('use_ocr') or 'true').strip().lower()
        use_ocr = use_ocr_raw in {'1', 'true', 'yes', 'y'}
        ocr_lang = (request.form.get('ocr_lang') or 'por').strip() or 'por'
        ocr_force_raw = (request.form.get('ocr_force') or 'false').strip().lower()
        ocr_force = ocr_force_raw in {'1', 'true', 'yes', 'y'}

        parsed = parse_diary_pdf(
            filepath,
            use_ocr=use_ocr,
            ocr_lang=ocr_lang,
            ocr_force=ocr_force,
        )
        preview_entries = []

        for index, raw_entry in enumerate(parsed.get('entries', [])):
            base_student_name = preferred_student_name or raw_entry.get('student_name', '')
            resolved_student_id, resolved_student_name, resolve_warnings = _resolve_student(
                preferred_student_id,
                base_student_name,
            )

            warnings = list(raw_entry.get('parse_warnings', []))
            warnings.extend(resolve_warnings)

            diary_date = raw_entry.get('diary_date', '')
            if diary_date and _diary_storage.has_date_conflict(
                resolved_student_id,
                resolved_student_name,
                diary_date,
            ):
                warnings.append('Já existe registro para este aluno na data informada')

            preview_entries.append({
                'preview_id': f'preview_{index + 1}',
                'student_id': resolved_student_id,
                'student_name': resolved_student_name,
                'diary_date': diary_date,
                'teachers': raw_entry.get('teachers', []),
                'answers': raw_entry.get('answers', {}),
                'open_obs': raw_entry.get('open_obs', ''),
                'status': raw_entry.get('status', 'draft'),
                'source': 'pdf_import',
                'parse_warnings': warnings,
            })

        if not preview_entries:
            preview_entries = [{
                'preview_id': 'preview_1',
                'student_id': None,
                'student_name': preferred_student_name,
                'diary_date': '',
                'teachers': [],
                'answers': {},
                'open_obs': '',
                'status': 'draft',
                'source': 'pdf_import',
                'parse_warnings': ['Nenhum bloco diário detectado no PDF'],
            }]

        return jsonify({
            'message': 'Preview gerado com sucesso',
            'entries': preview_entries,
            'metadata': parsed.get('metadata', {}),
            'warnings': parsed.get('warnings', []),
            'question_keys': list(QUESTION_PATTERNS.keys()),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route('/api/diary/import/commit', methods=['POST'])
def commit_diary_import():
    """Persiste entradas revisadas do preview de importação."""
    data = request.json or {}
    entries = data.get('entries') or []
    if not isinstance(entries, list) or not entries:
        return jsonify({'error': 'Nenhuma entrada fornecida para importação'}), 400

    saved_entries = []

    try:
        for entry in entries:
            student_id = (entry.get('student_id') or '').strip() or None
            student_name = (entry.get('student_name') or '').strip()

            resolved_student_id, resolved_student_name, resolve_warnings = _resolve_student(student_id, student_name)
            parse_warnings = list(entry.get('parse_warnings') or [])
            parse_warnings.extend(resolve_warnings)

            normalized_entry = {
                'student_id': resolved_student_id,
                'student_name': resolved_student_name,
                'teachers': entry.get('teachers') or [],
                'diary_date': (entry.get('diary_date') or '').strip(),
                'answers': entry.get('answers') or {},
                'open_obs': entry.get('open_obs') or '',
                'status': (entry.get('status') or 'draft').strip().lower(),
                'source': 'pdf_import',
                'parse_warnings': parse_warnings,
            }

            is_valid, error_message = _validate_commit_entry(normalized_entry)
            if not is_valid:
                return jsonify({'error': error_message, 'entry': normalized_entry}), 400

            if normalized_entry['diary_date'] and _diary_storage.has_date_conflict(
                normalized_entry['student_id'],
                normalized_entry['student_name'],
                normalized_entry['diary_date'],
            ):
                normalized_entry['parse_warnings'].append('Já existe registro para o mesmo aluno e data')

            saved = _diary_storage.save_entry(
                student_name=normalized_entry['student_name'],
                teachers=normalized_entry['teachers'],
                diary_date=normalized_entry['diary_date'],
                answers=normalized_entry['answers'],
                open_obs=normalized_entry['open_obs'],
                student_id=normalized_entry['student_id'],
                status=normalized_entry['status'],
                source=normalized_entry['source'],
                parse_warnings=normalized_entry['parse_warnings'],
            )
            saved_entries.append(saved)

        return jsonify({
            'message': 'Importação concluída com sucesso',
            'saved_count': len(saved_entries),
            'entries': saved_entries,
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================================================================
# PDI ROUTES
# ==================================================================

@app.route('/api/pdi/all', methods=['GET'])
def get_all_pdis():
    """Lista todos os PDIs com informações resumidas"""
    try:
        pdis = _pdi_storage.list_all_pdis()
        return jsonify(pdis)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/pdi/<student_name>', methods=['GET'])
def get_pdi_by_student(student_name):
    """Retorna o PDI de um aluno específico"""
    try:
        pdi = _pdi_storage.get_pdi_by_student(student_name)
        if not pdi:
            return jsonify({"error": "PDI não encontrado para este aluno"}), 404
        return jsonify(pdi)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/pdi/id/<pdi_id>', methods=['GET'])
def get_pdi_by_id(pdi_id):
    """Retorna um PDI específico por ID"""
    try:
        pdi = _pdi_storage.get_pdi(pdi_id)
        if not pdi:
            return jsonify({"error": "PDI não encontrado"}), 404
        return jsonify(pdi)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/pdi', methods=['POST'])
def create_pdi():
    """Cria um novo PDI"""
    data = request.json
    
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400
    
    required_fields = ['student_name', 'birth_date', 'guardians', 'diagnosis', 'class', 'teachers', 'trimesters']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Campo obrigatório ausente: {field}"}), 400
    
    # Validar que há pelo menos 1 guardian e 1 teacher
    if not data['guardians'] or len(data['guardians']) == 0:
        return jsonify({"error": "Pelo menos uma filiação é obrigatória"}), 400
    
    if not data['teachers'] or len(data['teachers']) == 0:
        return jsonify({"error": "Pelo menos um docente é obrigatório"}), 400
    
    try:
        pdi = _pdi_storage.save_pdi(
            student_name=data['student_name'],
            birth_date=data['birth_date'],
            guardians=data['guardians'],
            diagnosis=data['diagnosis'],
            class_name=data['class'],
            teachers=data['teachers'],
            trimesters=data['trimesters']
        )
        return jsonify({
            "message": "PDI criado com sucesso",
            "pdi": pdi
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/pdi/<pdi_id>', methods=['PUT'])
def update_pdi(pdi_id):
    """Atualiza um PDI existente"""
    data = request.json
    
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400
    
    required_fields = ['student_name', 'birth_date', 'guardians', 'diagnosis', 'class', 'teachers', 'trimesters']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Campo obrigatório ausente: {field}"}), 400
    
    # Validar que há pelo menos 1 guardian e 1 teacher
    if not data['guardians'] or len(data['guardians']) == 0:
        return jsonify({"error": "Pelo menos uma filiação é obrigatória"}), 400
    
    if not data['teachers'] or len(data['teachers']) == 0:
        return jsonify({"error": "Pelo menos um docente é obrigatório"}), 400
    
    try:
        pdi = _pdi_storage.update_pdi(
            pdi_id=pdi_id,
            student_name=data['student_name'],
            birth_date=data['birth_date'],
            guardians=data['guardians'],
            diagnosis=data['diagnosis'],
            class_name=data['class'],
            teachers=data['teachers'],
            trimesters=data['trimesters']
        )
        
        if not pdi:
            return jsonify({"error": "PDI não encontrado"}), 404
        
        return jsonify({
            "message": "PDI atualizado com sucesso",
            "pdi": pdi
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/pdi/<pdi_id>', methods=['DELETE'])
def delete_pdi(pdi_id):
    """Remove um PDI"""
    try:
        if _pdi_storage.delete_pdi(pdi_id):
            return jsonify({"message": "PDI removido com sucesso"})
        return jsonify({"error": "PDI não encontrado"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================================================================
# SCHOOL ROUTES
# ==================================================================

@app.route('/api/schools', methods=['GET'])
def get_all_schools():
    """Lista todas as escolas cadastradas"""
    try:
        schools = _school_storage.list_all_schools()
        return jsonify(schools)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/schools/<school_id>', methods=['GET'])
def get_school(school_id):
    """Retorna uma escola específica por ID"""
    try:
        school = _school_storage.get_school(school_id)
        if not school:
            return jsonify({"error": "Escola não encontrada"}), 404
        return jsonify(school)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/schools', methods=['POST'])
def create_school():
    """Cria um novo cadastro de escola"""
    data = request.json
    
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400
    
    try:
        school = _school_storage.create_school(data)
        return jsonify({
            "message": "Escola cadastrada com sucesso",
            "school": school
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/schools/<school_id>', methods=['PUT'])
def update_school(school_id):
    """Atualiza um cadastro de escola existente"""
    data = request.json
    
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400
    
    try:
        school = _school_storage.update_school(school_id, data)
        
        if not school:
            return jsonify({"error": "Escola não encontrada"}), 404
        
        return jsonify({
            "message": "Escola atualizada com sucesso",
            "school": school
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/schools/<school_id>', methods=['DELETE'])
def delete_school(school_id):
    """Remove um cadastro de escola"""
    try:
        if _school_storage.delete_school(school_id):
            return jsonify({"message": "Escola removida com sucesso"})
        return jsonify({"error": "Escola não encontrada"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================================================================
# STUDENT ROUTES
# ==================================================================

@app.route('/api/students', methods=['GET'])
def get_all_students():
    """Lista todos os alunos cadastrados"""
    try:
        students = _student_storage.list_all_students()
        return jsonify(students)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/students/<student_id>', methods=['GET'])
def get_student(student_id):
    """Retorna um aluno específico por ID"""
    try:
        student = _student_storage.get_student(student_id)
        if not student:
            return jsonify({"error": "Aluno não encontrado"}), 404
        return jsonify(student)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/students', methods=['POST'])
def create_student():
    """Cria um novo cadastro de aluno"""
    data = request.json
    
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400
    
    try:
        student = _student_storage.create_student(data)
        return jsonify({
            "message": "Aluno cadastrado com sucesso",
            "student": student
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/students/<student_id>', methods=['PUT'])
def update_student(student_id):
    """Atualiza um cadastro de aluno existente"""
    data = request.json
    
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400
    
    try:
        student = _student_storage.update_student(student_id, data)
        
        if not student:
            return jsonify({"error": "Aluno não encontrado"}), 404
        
        return jsonify({
            "message": "Aluno atualizado com sucesso",
            "student": student
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/students/<student_id>', methods=['DELETE'])
def delete_student(student_id):
    """Remove um cadastro de aluno"""
    try:
        if _student_storage.delete_student(student_id):
            return jsonify({"message": "Aluno removido com sucesso"})
        return jsonify({"error": "Aluno não encontrado"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================================================================
# TEACHER ROUTES
# ==================================================================

@app.route('/api/teachers', methods=['GET'])
def get_all_teachers():
    """Lista todos os docentes cadastrados."""
    try:
        teachers = _teacher_storage.list_all_teachers()
        return jsonify(teachers)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/teachers/<teacher_id>', methods=['GET'])
def get_teacher(teacher_id):
    """Retorna um docente específico por ID."""
    try:
        teacher = _teacher_storage.get_teacher(teacher_id)
        if not teacher:
            return jsonify({"error": "Docente não encontrado"}), 404
        return jsonify(teacher)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/teachers', methods=['POST'])
def create_teacher():
    """Cria um novo cadastro de docente."""
    data = request.json

    if not data:
        return jsonify({"error": "Dados inválidos"}), 400

    if not str(data.get('name', '')).strip():
        return jsonify({"error": "Nome do docente é obrigatório"}), 400

    try:
        teacher = _teacher_storage.create_teacher(data)
        return jsonify({
            "message": "Docente cadastrado com sucesso",
            "teacher": teacher
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/teachers/<teacher_id>', methods=['PUT'])
def update_teacher(teacher_id):
    """Atualiza um cadastro de docente existente."""
    data = request.json

    if not data:
        return jsonify({"error": "Dados inválidos"}), 400

    if not str(data.get('name', '')).strip():
        return jsonify({"error": "Nome do docente é obrigatório"}), 400

    try:
        teacher = _teacher_storage.update_teacher(teacher_id, data)

        if not teacher:
            return jsonify({"error": "Docente não encontrado"}), 404

        return jsonify({
            "message": "Docente atualizado com sucesso",
            "teacher": teacher
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/teachers/<teacher_id>', methods=['DELETE'])
def delete_teacher(teacher_id):
    """Remove um cadastro de docente."""
    try:
        if _teacher_storage.delete_teacher(teacher_id):
            return jsonify({"message": "Docente removido com sucesso"})
        return jsonify({"error": "Docente não encontrado"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================================================================
# RAG ROUTES
# ==================================================================

@app.route('/api/rag/upload', methods=['POST'])
def upload_document():
    """Upload e indexação de PDF no vector store"""
    engine = get_rag_engine()
    if engine is None:
        return jsonify({"error": "GOOGLE_API_KEY não configurada no .env"}), 503

    if 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    file = request.files['file']
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        return jsonify({"error": "Apenas arquivos PDF são permitidos"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        metadata_raw = request.form.get('metadata', '{}')
        metadata = json.loads(metadata_raw)
        metadata['file_name'] = filename

        from document_processor import extract_text_from_pdf, split_text_into_chunks, generate_embeddings
        text = extract_text_from_pdf(filepath)
        if not text:
            return jsonify({"error": "Não foi possível extrair texto do PDF"}), 400

        chunks = split_text_into_chunks(text)
        embeddings = [
            generate_embeddings(chunk, os.getenv('GOOGLE_API_KEY'), task_type="RETRIEVAL_DOCUMENT")
            for chunk in chunks
        ]
        doc_id = engine.vector_store.add_documents(chunks, embeddings, metadata)

        return jsonify({
            "message": "Documento indexado com sucesso",
            "doc_id": doc_id,
            "chunks_count": len(chunks),
            "file_name": filename
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route('/api/rag/students', methods=['GET'])
def get_rag_students():
    """Lista estudantes únicos agrupados por nome + escola"""
    engine = get_rag_engine()
    if engine is None:
        return jsonify({"error": "GOOGLE_API_KEY não configurada no .env"}), 503
    try:
        students = engine.vector_store.list_students()
        return jsonify(students)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/documents', methods=['GET'])
def get_rag_documents():
    """Lista documentos indexados no vector store"""
    engine = get_rag_engine()
    if engine is None:
        return jsonify({"error": "GOOGLE_API_KEY não configurada no .env"}), 503
    try:
        docs = engine.vector_store.list_documents()
        return jsonify(docs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/documents/<doc_id>', methods=['DELETE'])
def delete_rag_document(doc_id):
    """Remove documento do vector store"""
    engine = get_rag_engine()
    if engine is None:
        return jsonify({"error": "GOOGLE_API_KEY não configurada no .env"}), 503
    try:
        engine.vector_store.delete_document(doc_id)
        return jsonify({"message": "Documento removido com sucesso"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/reindex', methods=['POST'])
def reindex_documents():
    """Re-embeda todos os chunks existentes no ChromaDB com as configurações atuais.

    Necessário após atualizar chunk_size, overlap ou task_type dos embeddings.
    Lê os textos já armazenados (não precisa dos PDFs originais), deleta os
    embeddings antigos e reindexa com RETRIEVAL_DOCUMENT task_type.
    """
    engine = get_rag_engine()
    if engine is None:
        return jsonify({"error": "GOOGLE_API_KEY não configurada no .env"}), 503

    from document_processor import generate_embeddings

    try:
        collection = engine.vector_store.collection
        total = collection.count()
        if total == 0:
            return jsonify({"message": "Nenhum documento para reindexar", "reindexed": 0})

        # Buscar TODOS os chunks (textos + metadados + ids)
        all_data = collection.get(include=["documents", "metadatas", "embeddings"])
        ids = all_data["ids"]
        documents = all_data["documents"]
        metadatas = all_data["metadatas"]

        google_api_key = os.getenv('GOOGLE_API_KEY')

        # Re-gerar embeddings com task_type correto
        new_embeddings = []
        for chunk in documents:
            emb = generate_embeddings(chunk, google_api_key, task_type="RETRIEVAL_DOCUMENT")
            new_embeddings.append(emb)

        # Atualizar embeddings no ChromaDB (upsert preserva textos e metadados)
        collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=new_embeddings,
            metadatas=metadatas,
        )

        return jsonify({
            "message": "Reindexação concluída com sucesso",
            "reindexed": len(ids),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/chat', methods=['POST'])
def rag_chat():
    """Chat com contexto RAG"""
    engine = get_rag_engine()
    if engine is None:
        return jsonify({"error": "GOOGLE_API_KEY não configurada no .env"}), 503

    data = request.json or {}
    message = data.get('message', '').strip()
    if not message:
        return jsonify({"error": "Mensagem não fornecida"}), 400

    try:
        student_name = data.get('student_name', '').strip()
        school = data.get('school', '').strip()
        context_filter = None
        if student_name and school:
            context_filter = {"$and": [{"student_name": {"$eq": student_name}}, {"school": {"$eq": school}}]}
        elif student_name:
            context_filter = {"student_name": {"$eq": student_name}}

        session_id = data.get('session_id') or (f"{student_name}__{school}" if student_name else 'default')

        result = engine.query(
            message=message,
            session_id=session_id,
            context_filter=context_filter,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/generate-pei', methods=['POST'])
def generate_pei():
    """Gera PEI estruturado completo e salva como PDF"""
    engine = get_rag_engine()
    if engine is None:
        return jsonify({"error": "GOOGLE_API_KEY não configurada no .env"}), 503

    data = request.json or {}
    student_name = data.get('student_name', '').strip()
    school = data.get('school', '').strip()

    if not student_name or not school:
        return jsonify({"error": "Nome do estudante e escola são obrigatórios"}), 400

    try:
        result = engine.generate_pei(
            student_name=student_name,
            school=school,
            additional_info=data.get('additional_info', ''),
        )
        markdown_text = result['pei']

        # Gerar PDF
        from pdf_generator import markdown_to_pdf
        from datetime import datetime
        safe_name = student_name.replace(' ', '_')
        pdf_filename = f"PEI_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf_path = os.path.join(PEIS_FOLDER, pdf_filename)
        markdown_to_pdf(markdown_text, student_name, school, pdf_path)

        # Salvar no índice
        entry = _pei_storage.save(
            student_name=student_name,
            school=school,
            markdown_text=markdown_text,
            pdf_path=pdf_path,
        )

        result['pei_id'] = entry['id']
        result['pdf_url'] = f"/api/rag/peis/{entry['id']}/pdf"
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/peis', methods=['GET'])
def list_peis():
    """Lista todos os PEIs gerados"""
    try:
        student_filter = request.args.get('student_name')
        school_filter = request.args.get('school')
        peis = _pei_storage.list_all()
        if student_filter:
            peis = [p for p in peis if p['student_name'] == student_filter]
        if school_filter:
            peis = [p for p in peis if p['school'] == school_filter]
        return jsonify(peis)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/peis/<pei_id>/pdf', methods=['GET'])
def get_pei_pdf(pei_id):
    """Serve o arquivo PDF de um PEI"""
    pdf_path = _pei_storage.get_pdf_path(pei_id)
    if not pdf_path:
        return jsonify({"error": "PEI não encontrado"}), 404
    return send_file(pdf_path, mimetype='application/pdf')


@app.route('/api/rag/peis/<pei_id>', methods=['DELETE'])
def delete_pei(pei_id):
    """Remove um PEI gerado"""
    if _pei_storage.delete(pei_id):
        return jsonify({"message": "PEI removido"})
    return jsonify({"error": "PEI não encontrado"}), 404


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '0.0.0.0')
    debug = DEBUG_MODE
    
    app.run(host=host, port=port, debug=debug)
