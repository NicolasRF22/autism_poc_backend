from pathlib import Path
from diary_pdf_parser import extract_pages_images, extract_checkbox_answers_from_page

images = extract_pages_images('../DIÁRIO ESCOLAR 2025 -  ALVINA.pdf', scale=3.0, page_indices=[0, 1, 2])
lines = []
for idx in [0, 1, 2]:
    answers = extract_checkbox_answers_from_page(images[idx], lang='por')
    lines.append(f'DIA_{idx+1}: {answers}')

out_path = Path('/home/nicolas/Aut/quick_checkbox_test.txt')
out_path.write_text('\n'.join(lines), encoding='utf-8')
print(str(out_path))
