import re
import importlib
import unicodedata
import os
import statistics
from datetime import datetime
from typing import Dict, List, Optional, Tuple


QUESTION_PATTERNS = {
    "lanchou": [r"lanchou"],
    "participou_brincadeira": [r"participou\s+da\s+brincadeira", r"atividade\s+coletiva"],
    "atencao_professora": [r"aten[cç][aã]o\s+[àa]\s+fala\s+da\s+professora", r"aten[cç][aã]o\s+professora"],
    "interesse_atividades": [r"interesse\s+para\s+as\s+atividades", r"demonstrou\s+interesse"],
    "realizou_atividades": [r"realizou\s+as\s+atividades\s+propostas", r"realizou\s+as\s+atividades"],
    "uso_banheiro": [r"uso\s+do\s+banheiro", r"fez\s+uso\s+do\s+banheiro"],
    "cumpriu_combinados": [r"cumpriu\s+os\s+combinados"],
}

QUESTION_ORDER = [
    "lanchou",
    "participou_brincadeira",
    "atencao_professora",
    "interesse_atividades",
    "realizou_atividades",
    "uso_banheiro",
    "cumpriu_combinados",
]

QUESTION_LINE_HINTS = {
    "lanchou": ["lanchou"],
    "participou_brincadeira": ["participou", "coletiva"],
    "atencao_professora": ["deu", "atencao"],
    "interesse_atividades": ["demonstrou", "interesse"],
    "realizou_atividades": ["realizou", "propostas"],
    "uso_banheiro": ["banheiro", "fez"],
    "cumpriu_combinados": ["cumpriu", "combinados"],
}

ANSWER_BY_COLUMN = {
    "sim": "Sim",
    "nao": "Não",
    "parcialmente": "Parcialmente",
}

ANSWER_REGEX = re.compile(r"\b(sim|n[aã]o|nao|parcialmente)\b", re.IGNORECASE)
DATE_REGEX = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{2}-\d{2})\b")

HEADER_REGEX = re.compile(
    r"D\s*I\s*[AÁÀÃÂ]\s*R\s*I\s*O\s*D\s*E\s*A\s*C\s*O\s*M\s*P\s*A\s*N\s*H\s*A\s*M\s*E\s*N\s*T\s*O\s*I\s*N\s*D\s*I\s*V\s*I\s*D\s*U\s*A\s*L",
    re.IGNORECASE,
)
ALUNO_LABEL_REGEX = re.compile(r"A\s*L\s*U\s*N\s*O\s*:\s*", re.IGNORECASE)
PROF_LABEL_REGEX = re.compile(r"P\s*R\s*O\s*F\s*E\s*S\s*S\s*O\s*R\s*\(\s*A\s*\)\s*:\s*", re.IGNORECASE)
DIA_LETIVO_LABEL_REGEX = re.compile(r"D\s*I\s*A\s*L\s*E\s*T\s*I\s*V\s*O\s*:\s*", re.IGNORECASE)
DATA_LABEL_REGEX = re.compile(r"D\s*A\s*T\s*A\s*:\s*", re.IGNORECASE)


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.lower().split())


def normalize_text_compact(value: str) -> str:
    return normalize_text(value).replace(" ", "")


def extract_pages_text_from_pdf(pdf_path: str) -> List[str]:
    pypdf2 = importlib.import_module("PyPDF2")

    pages: List[str] = []
    with open(pdf_path, "rb") as file:
        reader = pypdf2.PdfReader(file)
        for page in reader.pages:
            page_text = page.extract_text()
            pages.append(page_text or "")
    return pages


def extract_pages_text_with_ocr(pdf_path: str, ocr_lang: str = "por") -> List[str]:
    pypdfium2 = importlib.import_module("pypdfium2")
    pytesseract = importlib.import_module("pytesseract")

    configured_tesseract = os.getenv("TESSERACT_CMD", "").strip()
    if configured_tesseract:
        pytesseract.pytesseract.tesseract_cmd = configured_tesseract
    elif os.name != "nt" and os.path.exists("/usr/bin/tesseract"):
        pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

    pdf = pypdfium2.PdfDocument(pdf_path)
    pages_text: List[str] = []

    for page_index in range(len(pdf)):
        page = pdf[page_index]
        pil_image = page.render(scale=3).to_pil()
        text = pytesseract.image_to_string(pil_image, lang=ocr_lang)
        pages_text.append(text or "")

    return pages_text


def extract_pages_images(pdf_path: str, scale: float = 3.0, page_indices: Optional[List[int]] = None) -> Dict[int, object]:
    pypdfium2 = importlib.import_module("pypdfium2")
    pdf = pypdfium2.PdfDocument(pdf_path)
    if page_indices is None:
        page_indices = list(range(len(pdf)))

    images_by_index: Dict[int, object] = {}
    for page_index in sorted(set(page_indices)):
        if page_index < 0 or page_index >= len(pdf):
            continue
        images_by_index[page_index] = pdf[page_index].render(scale=scale).to_pil()
    return images_by_index


def extract_pages_text_with_ocr_fallback(pdf_path: str, ocr_lang: str = "por") -> Tuple[List[str], str]:
    tried_langs = []
    candidate_langs = [ocr_lang]
    if ocr_lang != "eng":
        candidate_langs.append("eng")

    last_error: Optional[Exception] = None

    for lang in candidate_langs:
        tried_langs.append(lang)
        try:
            pages = extract_pages_text_with_ocr(pdf_path, ocr_lang=lang)
            return pages, lang
        except Exception as error:
            last_error = error

    tried_str = ", ".join(tried_langs)
    raise RuntimeError(f"OCR falhou para idiomas [{tried_str}]: {last_error}")


def _setup_tesseract_cmd_for_runtime(pytesseract_module):
    configured_tesseract = os.getenv("TESSERACT_CMD", "").strip()
    if configured_tesseract:
        pytesseract_module.pytesseract.tesseract_cmd = configured_tesseract
    elif os.name != "nt" and os.path.exists("/usr/bin/tesseract"):
        pytesseract_module.pytesseract.tesseract_cmd = "/usr/bin/tesseract"


def _extract_lines_from_tesseract(image, lang: str) -> List[Dict]:
    pytesseract = importlib.import_module("pytesseract")
    _setup_tesseract_cmd_for_runtime(pytesseract)

    data = pytesseract.image_to_data(
        image,
        lang=lang,
        output_type=pytesseract.Output.DICT,
        config="--psm 6",
    )

    line_map: Dict[Tuple[int, int, int], Dict] = {}
    total = len(data.get("text", []))
    for i in range(total):
        raw = (data["text"][i] or "").strip()
        if not raw:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])

        left = int(data["left"][i])
        top = int(data["top"][i])
        width = int(data["width"][i])
        height = int(data["height"][i])
        right = left + width
        bottom = top + height

        if key not in line_map:
            line_map[key] = {
                "text_parts": [],
                "left": left,
                "top": top,
                "right": right,
                "bottom": bottom,
            }

        line_map[key]["text_parts"].append(raw)
        line_map[key]["left"] = min(line_map[key]["left"], left)
        line_map[key]["top"] = min(line_map[key]["top"], top)
        line_map[key]["right"] = max(line_map[key]["right"], right)
        line_map[key]["bottom"] = max(line_map[key]["bottom"], bottom)

    lines = []
    for value in line_map.values():
        joined = " ".join(value["text_parts"]).strip()
        if not joined:
            continue
        lines.append(
            {
                "text": joined,
                "text_norm": normalize_text(joined),
                "left": value["left"],
                "top": value["top"],
                "right": value["right"],
                "bottom": value["bottom"],
                "x_center": int((value["left"] + value["right"]) / 2),
                "y_center": int((value["top"] + value["bottom"]) / 2),
            }
        )

    return sorted(lines, key=lambda line: (line["top"], line["left"]))


def _infer_activity_columns(lines: List[Dict]) -> Dict[str, int]:
    sim_x = []
    nao_x = []
    parcial_x = []

    for line in lines:
        compact = normalize_text_compact(line["text"])
        if compact == "sim":
            sim_x.append(line["x_center"])
        elif compact in {"nao", "n5o", "n&o"}:
            nao_x.append(line["x_center"])
        elif "parcialmente" in compact or compact.startswith("parcial"):
            parcial_x.append(line["x_center"])

    columns = {}
    if sim_x:
        columns["sim"] = int(statistics.median(sim_x))
    if nao_x:
        columns["nao"] = int(statistics.median(nao_x))
    if parcial_x:
        columns["parcialmente"] = int(statistics.median(parcial_x))

    return columns


def _infer_question_rows(lines: List[Dict]) -> Dict[str, int]:
    rows = {}
    for question_id in QUESTION_ORDER:
        hints = QUESTION_LINE_HINTS[question_id]
        for line in lines:
            compact = normalize_text_compact(line["text"])
            if all(hint in compact for hint in hints):
                rows[question_id] = line["y_center"]
                break
    return rows


def _measure_darkness(gray_pixels, x_center: int, y_center: int, radius: int = 16) -> float:
    width = len(gray_pixels[0])
    height = len(gray_pixels)
    left = max(0, x_center - radius)
    right = min(width, x_center + radius)
    top = max(0, y_center - radius)
    bottom = min(height, y_center + radius)

    if left >= right or top >= bottom:
        return 0.0

    total = 0
    dark = 0
    for y in range(top, bottom):
        row = gray_pixels[y]
        for x in range(left, right):
            total += 1
            if row[x] < 165:
                dark += 1

    if total == 0:
        return 0.0
    return dark / total


def extract_checkbox_answers_from_page(image, lang: str = "por") -> Dict[str, str]:
    lines = _extract_lines_from_tesseract(image, lang=lang)
    columns = _infer_activity_columns(lines)
    rows = _infer_question_rows(lines)

    if len(columns) < 3 or len(rows) < 5:
        return {}

    gray = image.convert("L")
    width, height = gray.size
    gray_data = list(gray.getdata())
    gray_pixels = [gray_data[i * width : (i + 1) * width] for i in range(height)]

    answers: Dict[str, str] = {}
    ordered_columns = ["sim", "nao", "parcialmente"]

    for question_id, row_y in rows.items():
        scores = {}
        for column_name in ordered_columns:
            x_center = columns[column_name]
            scores[column_name] = _measure_darkness(gray_pixels, x_center, row_y)

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best_name, best_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0

        if best_score < 0.040:
            continue
        if (best_score - second_score) < 0.010:
            continue

        answers[question_id] = ANSWER_BY_COLUMN[best_name]

    return answers


def normalize_answer(raw: str) -> Optional[str]:
    token = normalize_text(raw)
    if token == "sim":
        return "Sim"
    if token in {"nao", "não"}:
        return "Não"
    if token == "parcialmente":
        return "Parcialmente"
    return None


def parse_date(raw: str) -> Optional[str]:
    cleaned = raw.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %m %Y"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def split_entries_across_pages(pages_text: List[str]) -> List[Dict]:
    entries: List[Dict] = []
    current_entry: Optional[Dict] = None

    for page_index, page_text in enumerate(pages_text):
        if not page_text.strip():
            continue

        header_matches = list(HEADER_REGEX.finditer(page_text))

        if not header_matches:
            if current_entry is not None:
                current_entry["text"] += "\n" + page_text
                current_entry["end_page"] = page_index + 1
            continue

        cursor = 0
        for idx, match in enumerate(header_matches):
            start = match.start()
            next_start = header_matches[idx + 1].start() if idx + 1 < len(header_matches) else len(page_text)

            if current_entry is not None and start > cursor:
                current_entry["text"] += "\n" + page_text[cursor:start]
                current_entry["end_page"] = page_index + 1

            if current_entry is not None:
                entries.append(current_entry)

            current_entry = {
                "start_page": page_index + 1,
                "end_page": page_index + 1,
                "text": page_text[start:next_start],
            }
            cursor = next_start

    if current_entry is not None:
        entries.append(current_entry)

    return entries


def _score_entries(entries: List[Dict]) -> int:
    blocks_score = len(entries) * 20
    answers_score = sum(len(entry.get("answers", {})) for entry in entries)
    dates_score = sum(1 for entry in entries if entry.get("diary_date")) * 5
    teachers_score = sum(1 for entry in entries if entry.get("teachers")) * 3
    return blocks_score + answers_score + dates_score + teachers_score


def extract_student_name(block: str) -> Optional[str]:
    aluno_match = ALUNO_LABEL_REGEX.search(block)
    if not aluno_match:
        return None

    start = aluno_match.end()
    end_candidates = [PROF_LABEL_REGEX.search(block, start), DIA_LETIVO_LABEL_REGEX.search(block, start)]
    end_candidates = [candidate for candidate in end_candidates if candidate]

    if not end_candidates:
        student_raw = block[start:start + 120]
    else:
        student_raw = block[start:min(candidate.start() for candidate in end_candidates)]

    student_name = " ".join(student_raw.replace("\n", " ").split()).strip(" -:")
    return student_name or None


def extract_teachers(text_block: str) -> List[str]:
    prof_match = PROF_LABEL_REGEX.search(text_block)
    if not prof_match:
        return []

    start = prof_match.end()
    end_candidates = [DIA_LETIVO_LABEL_REGEX.search(text_block, start), DATA_LABEL_REGEX.search(text_block, start)]
    end_candidates = [candidate for candidate in end_candidates if candidate]

    if not end_candidates:
        teachers_raw = text_block[start:start + 120]
    else:
        teachers_raw = text_block[start:min(candidate.start() for candidate in end_candidates)]

    raw = " ".join(teachers_raw.replace("\n", " ").split())
    parts = re.split(r",|;|/|\se\s", raw)
    teachers = [p.strip(" -:") for p in parts if p.strip(" -:")]
    if teachers:
        return teachers

    return []


def extract_observations(text_block: str) -> str:
    pattern = re.compile(
        r"observa[cç][oõ]es?\s*:?\s*(.+)$",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(text_block)
    if not match:
        return ""

    obs = match.group(1).strip()
    obs = re.split(r"\n\s*(?:aluno\(a\)|dia\s+letivo|data)\s*:", obs, flags=re.IGNORECASE)[0].strip()
    return obs


def extract_date_from_block(block: str) -> Optional[str]:
    direct_match = DATE_REGEX.search(block)
    if direct_match:
        parsed = parse_date(direct_match.group(1))
        if parsed:
            return parsed

    data_match = DATA_LABEL_REGEX.search(block)
    if data_match:
        window = block[data_match.end():data_match.end() + 80]
        triple = re.search(r"(\d{1,2})\D+(\d{1,2})\D+(\d{4})", window)
        if triple:
            day, month, year = triple.groups()
            parsed = parse_date(f"{int(day):02d}/{int(month):02d}/{year}")
            if parsed:
                return parsed

    return None


def extract_answer_for_question(block: str, patterns: List[str]) -> Optional[str]:
    normalized_block = normalize_text(block)

    for pattern in patterns:
        regex = re.compile(pattern)
        match = regex.search(normalized_block)
        if not match:
            continue

        start = match.end()
        window = normalized_block[start:start + 120]
        answer_match = ANSWER_REGEX.search(window)
        if answer_match:
            return normalize_answer(answer_match.group(1))

    return None


def parse_day_block(block: str, fallback_student_name: Optional[str], start_page: int, end_page: int) -> Dict:
    answers = {}
    warnings = []

    for question_id, patterns in QUESTION_PATTERNS.items():
        answer = extract_answer_for_question(block, patterns)
        if answer:
            answers[question_id] = answer
        else:
            warnings.append(f"Resposta não encontrada para: {question_id}")

    teachers = extract_teachers(block)
    if not teachers:
        warnings.append("Professor(es) não identificado(s) no bloco")

    diary_date = extract_date_from_block(block) or ""
    if not diary_date:
        warnings.append("Data não identificada no bloco")

    student_name = extract_student_name(block) or fallback_student_name or ""
    if not student_name:
        warnings.append("Aluno não identificado no bloco")

    open_obs = extract_observations(block)

    return {
        "student_name": student_name,
        "diary_date": diary_date,
        "teachers": teachers,
        "answers": answers,
        "open_obs": open_obs,
        "status": "draft",
        "source": "pdf_import",
        "page_range": {
            "start": start_page,
            "end": end_page,
        },
        "parse_warnings": warnings,
    }


def _merge_checkbox_answers(entry: Dict, checkbox_answers: Dict[str, str]):
    if not checkbox_answers:
        return

    answers = entry.get("answers") or {}
    answers.update(checkbox_answers)
    entry["answers"] = answers

    warnings = entry.get("parse_warnings") or []
    remaining_warnings = []
    for warning in warnings:
        if warning.startswith("Resposta não encontrada para:"):
            question_id = warning.split(":", 1)[1].strip()
            if question_id in checkbox_answers:
                continue
        remaining_warnings.append(warning)
    entry["parse_warnings"] = remaining_warnings


def build_empty_draft(student_name: Optional[str] = None) -> Dict:
    return {
        "student_name": student_name or "",
        "diary_date": "",
        "teachers": [],
        "answers": {},
        "open_obs": "",
        "status": "draft",
        "source": "pdf_import",
        "parse_warnings": [
            "Não foi possível extrair texto pesquisável do PDF.",
            "Rascunho criado para preenchimento manual.",
        ],
    }


def _parse_entries_from_pages(pages_text: List[str]) -> Tuple[List[Dict], Dict]:
    full_text = "\n".join(pages_text).strip()

    if not full_text:
        return [build_empty_draft()], {
            "extracted_text": False,
            "blocks_detected": 0,
            "student_name_detected": "",
            "pages_total": len(pages_text),
        }

    fallback_student_name = extract_student_name(full_text)
    day_blocks = split_entries_across_pages(pages_text)

    entries = [
        parse_day_block(
            block=day_block["text"],
            fallback_student_name=fallback_student_name,
            start_page=day_block["start_page"],
            end_page=day_block["end_page"],
        )
        for day_block in day_blocks
    ]

    if not entries:
        entries = [build_empty_draft(student_name=fallback_student_name)]

    metadata = {
        "extracted_text": True,
        "blocks_detected": len(day_blocks),
        "student_name_detected": fallback_student_name or "",
        "pages_total": len(pages_text),
    }
    return entries, metadata


def _apply_checkbox_calibration(
    entries: List[Dict],
    pages_images_by_index: Dict[int, object],
    ocr_lang: str,
    max_entries: Optional[int] = None,
) -> int:
    calibrated = 0
    target_entries = entries if max_entries is None else entries[:max_entries]
    for entry in target_entries:
        page_range = entry.get("page_range") or {}
        start_page = page_range.get("start")
        if not start_page:
            continue

        page_index = int(start_page) - 1
        if page_index not in pages_images_by_index:
            continue

        try:
            checkbox_answers = extract_checkbox_answers_from_page(pages_images_by_index[page_index], lang=ocr_lang)
            if checkbox_answers:
                _merge_checkbox_answers(entry, checkbox_answers)
                calibrated += 1
        except Exception:
            continue
    return calibrated


def parse_diary_pdf(
    pdf_path: str,
    use_ocr: bool = True,
    ocr_lang: str = "por",
    ocr_force: bool = False,
    checkbox_calibration_max_entries: Optional[int] = 30,
) -> Dict:
    warnings: List[str] = []

    native_pages = extract_pages_text_from_pdf(pdf_path)
    native_entries, native_metadata = _parse_entries_from_pages(native_pages)
    native_score = _score_entries(native_entries)

    chosen_entries = native_entries
    chosen_metadata = {
        **native_metadata,
        "source": "native_pdf_text",
        "ocr_attempted": False,
        "ocr_used": False,
        "native_score": native_score,
    }

    if use_ocr:
        chosen_metadata["ocr_attempted"] = True
        try:
            ocr_pages, ocr_lang_used = extract_pages_text_with_ocr_fallback(pdf_path, ocr_lang=ocr_lang)
            ocr_entries, ocr_metadata = _parse_entries_from_pages(ocr_pages)
            ocr_score = _score_entries(ocr_entries)

            chosen_metadata["ocr_score"] = ocr_score
            chosen_metadata["ocr_lang_used"] = ocr_lang_used

            should_use_ocr = ocr_force or ocr_score > native_score
            if should_use_ocr:
                chosen_entries = ocr_entries
                chosen_metadata = {
                    **ocr_metadata,
                    "source": "ocr_text",
                    "ocr_attempted": True,
                    "ocr_used": True,
                    "native_score": native_score,
                    "ocr_score": ocr_score,
                }
            else:
                warnings.append("OCR executado, mas texto nativo apresentou melhor qualidade.")

        except ModuleNotFoundError as error:
            warnings.append(
                f"OCR indisponível: dependência ausente ({str(error)})."
            )
            warnings.append("Instale: pytesseract e pypdfium2, além do binário Tesseract no sistema.")
        except Exception as error:
            warnings.append(f"Falha ao executar OCR: {str(error)}")

    if not chosen_entries:
        chosen_entries = [build_empty_draft()]

    try:
        target_entries = chosen_entries if checkbox_calibration_max_entries is None else chosen_entries[:checkbox_calibration_max_entries]
        target_page_indices = []
        for entry in target_entries:
            page_range = entry.get("page_range") or {}
            start_page = page_range.get("start")
            if start_page:
                target_page_indices.append(int(start_page) - 1)

        pages_images_by_index = extract_pages_images(
            pdf_path,
            scale=3.0,
            page_indices=target_page_indices,
        )
        calibrated_entries = _apply_checkbox_calibration(
            chosen_entries,
            pages_images_by_index,
            ocr_lang=ocr_lang,
            max_entries=checkbox_calibration_max_entries,
        )
        chosen_metadata["checkbox_calibration_entries"] = calibrated_entries
        chosen_metadata["checkbox_calibration_limit"] = checkbox_calibration_max_entries
    except Exception as error:
        warnings.append(f"Calibração de checkbox indisponível: {str(error)}")

    return {
        "entries": chosen_entries,
        "warnings": warnings,
        "metadata": chosen_metadata,
    }
