"""Defaults and normalization helpers for PDI trimesters."""

from typing import Dict, List, Optional, Sequence


PDI_SUBJECTS_INFANTIL = [
    'eu_o_outro_e_o_nos',
    'corpo_gestos_e_movimentos',
    'tracos_sons_cores_e_formas',
    'escuta_faca_pensamento_e_imaginacao',
    'espacos_tempos_relacoes_e_transformacoes',
]

PDI_SUBJECTS_FUNDAMENTAL_I = [
    'lingua_portuguesa',
    'matematica',
    'historia',
    'geografia',
    'ciencias',
    'ensino_religioso',
    'arte',
    'educacao_fisica',
]

PDI_SUBJECTS = [*PDI_SUBJECTS_INFANTIL, *PDI_SUBJECTS_FUNDAMENTAL_I]

INFANTIL_GRADES = {
    '1° Ano do Infantil',
    '2° Ano do Infantil',
    '3° Ano do Infantil',
}

FUNDAMENTAL_I_GRADES = {
    '1° Ano do Fundamental I',
    '2° Ano do Fundamental I',
    '3° Ano do Fundamental I',
    '4° Ano do Fundamental I',
    '5° Ano do Fundamental I',
}


def get_pdi_subject_ids_for_grade(grade: Optional[str]) -> List[str]:
    normalized_grade = str(grade or '').strip()
    if normalized_grade in INFANTIL_GRADES:
        return PDI_SUBJECTS_INFANTIL
    if normalized_grade in FUNDAMENTAL_I_GRADES:
        return PDI_SUBJECTS_FUNDAMENTAL_I
    return PDI_SUBJECTS_FUNDAMENTAL_I


def create_empty_subject_row() -> Dict[str, str]:
    return {
        'habilidades': '',
        'adaptacoes': '',
        'aprendizagens': '',
    }


def create_empty_trimester(subject_ids: Optional[Sequence[str]] = None) -> Dict:
    trimester = {
        'relatorio_descritivo': {},
    }
    for subject_id in list(subject_ids or PDI_SUBJECTS):
        trimester[subject_id] = [create_empty_subject_row()]
    return trimester


def _normalize_rows(rows) -> List[Dict[str, str]]:
    if not isinstance(rows, list) or not rows:
        return [create_empty_subject_row()]

    normalized_rows = []
    for row in rows:
        if not isinstance(row, dict):
            normalized_rows.append(create_empty_subject_row())
            continue

        normalized_rows.append({
            'habilidades': str(row.get('habilidades', '') or ''),
            'adaptacoes': str(row.get('adaptacoes', '') or ''),
            'aprendizagens': str(row.get('aprendizagens', '') or ''),
        })

    return normalized_rows or [create_empty_subject_row()]


def normalize_trimester(trimester, subject_ids: Optional[Sequence[str]] = None) -> Dict:
    if not isinstance(trimester, dict):
        return create_empty_trimester(subject_ids)

    normalized = dict(trimester)
    relatorio = normalized.get('relatorio_descritivo')
    normalized['relatorio_descritivo'] = relatorio if isinstance(relatorio, dict) else {}

    for subject_id in list(subject_ids or PDI_SUBJECTS):
        normalized[subject_id] = _normalize_rows(normalized.get(subject_id))

    return normalized


def normalize_trimesters(trimesters, subject_ids: Optional[Sequence[str]] = None) -> Dict:
    if not isinstance(trimesters, dict):
        return {
            '1': create_empty_trimester(subject_ids),
            '2': create_empty_trimester(subject_ids),
            '3': create_empty_trimester(subject_ids),
        }

    normalized = dict(trimesters)
    for trimester_key in ['1', '2', '3']:
        normalized[trimester_key] = normalize_trimester(normalized.get(trimester_key), subject_ids=subject_ids)

    return normalized