import glob
import json
from datetime import datetime
from pathlib import Path

from diary_pdf_parser import parse_diary_pdf


def main():
    pdf_candidates = glob.glob('../DIA*ALVINA.pdf')
    if not pdf_candidates:
        raise RuntimeError('PDF de diário não encontrado')

    pdf_path = pdf_candidates[0]
    result = parse_diary_pdf(
        pdf_path,
        use_ocr=False,
        ocr_lang='por',
        checkbox_calibration_max_entries=3,
    )
    entries = result.get('entries', [])[:3]
    metadata = result.get('metadata', {})

    question_order = [
        'lanchou',
        'participou_brincadeira',
        'atencao_professora',
        'interesse_atividades',
        'realizou_atividades',
        'uso_banheiro',
        'cumpriu_combinados',
    ]

    question_labels = {
        'lanchou': 'Lanchou?',
        'participou_brincadeira': 'Participou da brincadeira/atividade coletiva?',
        'atencao_professora': 'Deu atenção à fala da professora?',
        'interesse_atividades': 'Demonstrou interesse para as atividades?',
        'realizou_atividades': 'Realizou as atividades propostas?',
        'uso_banheiro': 'Fez uso do banheiro?',
        'cumpriu_combinados': 'Cumpriu os combinados?',
    }

    lines = []
    lines.append('DEBUG CALIBRADO - PRIMEIROS 3 DIAS')
    lines.append(f'Gerado em: {datetime.now().isoformat()}')
    lines.append('')
    lines.append('METADADOS')
    lines.append(f'- Fonte: {metadata.get("source")}')
    lines.append(f'- OCR usado: {metadata.get("ocr_used")}')
    lines.append(f'- Idioma OCR: {metadata.get("ocr_lang_used")}')
    lines.append(f'- Blocos detectados: {metadata.get("blocks_detected")}')
    lines.append(f'- Native score: {metadata.get("native_score")}')
    lines.append(f'- OCR score: {metadata.get("ocr_score")}')
    lines.append(f'- Entradas com calibração checkbox: {metadata.get("checkbox_calibration_entries")}')
    lines.append(f'- Warnings globais: {json.dumps(result.get("warnings", []), ensure_ascii=False)}')
    lines.append('')

    for index, entry in enumerate(entries, start=1):
        lines.append(f'===== DIA {index} =====')
        lines.append(f'Data: {entry.get("diary_date", "")}')
        page_range = entry.get('page_range', {}) or {}
        lines.append(f'Páginas: {page_range.get("start", "?")} - {page_range.get("end", "?")}')
        lines.append(f'Aluno: {entry.get("student_name", "")}')
        lines.append(f'Professores: {", ".join(entry.get("teachers", []))}')

        answers = entry.get('answers', {}) or {}
        lines.append('Respostas capturadas:')
        for question_id in question_order:
            answer = answers.get(question_id, '[NÃO CAPTURADO]')
            lines.append(f'  - {question_labels[question_id]} -> {answer}')

        warnings = entry.get('parse_warnings', []) or []
        if warnings:
            lines.append(f'Warnings: {json.dumps(warnings, ensure_ascii=False)}')
        else:
            lines.append('Warnings: [SEM WARNINGS]')

        open_obs = (entry.get('open_obs') or '').strip()
        lines.append('Observações:')
        lines.append(open_obs if open_obs else '[VAZIO OU NÃO CAPTURADO]')
        lines.append('')

    output_path = Path('/home/nicolas/Aut/debug_primeiros_3_dias_calibrado.txt')
    output_path.write_text('\n'.join(lines), encoding='utf-8')
    print(str(output_path))


if __name__ == '__main__':
    main()
