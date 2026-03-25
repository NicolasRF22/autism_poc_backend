"""Gera PDFs formatados a partir de texto Markdown usando fpdf2 + DejaVu (Unicode)."""
import re
from fpdf import FPDF
from fpdf.enums import XPos, YPos

_FONT_DIR = "/usr/share/fonts/truetype/dejavu"
_FONT_REGULAR = f"{_FONT_DIR}/DejaVuSans.ttf"
_FONT_BOLD    = f"{_FONT_DIR}/DejaVuSans-Bold.ttf"

_BULLET_RE = re.compile(r"^(\s*)[-*\u2022]\s+(.+)$")
_NUM_RE    = re.compile(r"^(\s*)\d+[.)]\s+(.+)$")


def _strip_bold(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def _parse_table(lines: list) -> list:
    rows = []
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        if re.match(r"^\|[\s:|\-]+\|$", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)
    return rows


class PEI_PDF(FPDF):
    def __init__(self, student_name: str, school: str):
        super().__init__()
        self.student_name = student_name
        self.school = school
        self.add_font("DejaVu",  "",   _FONT_REGULAR)
        self.add_font("DejaVu",  "B",  _FONT_BOLD)
        self.add_font("DejaVu",  "I",  _FONT_REGULAR)
        self.add_font("DejaVu",  "BI", _FONT_BOLD)
        self.set_auto_page_break(auto=True, margin=20)
        self.add_page()
        self._set_cover()

    # ------------------------------------------------------------------
    # Header / Footer
    # ------------------------------------------------------------------
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("DejaVu", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8,
                  f"PEI \u2014 {self.student_name} \u00b7 {self.school}",
                  align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(200, 200, 200)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)
        self.set_text_color(0, 0, 0)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-15)
        self.set_font("DejaVu", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"P\u00e1gina {self.page_no() - 1}", align="C")
        self.set_text_color(0, 0, 0)

    # ------------------------------------------------------------------
    # Capa
    # ------------------------------------------------------------------
    def _set_cover(self):
        self.set_auto_page_break(False)

        self.set_fill_color(74, 144, 217)
        self.rect(0, 0, self.w, self.h, style="F")

        box_h = 80
        box_y = (self.h - box_h) / 2
        self.set_fill_color(255, 255, 255)
        self.rect(self.l_margin, box_y,
                  self.w - self.l_margin - self.r_margin, box_h, style="F")

        self.set_y(box_y + 10)
        self.set_font("DejaVu", "B", 20)
        self.set_text_color(30, 80, 160)
        self.cell(0, 12, "Plano Educacional Individualizado", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_font("DejaVu", "", 12)
        self.set_text_color(74, 144, 217)
        self.cell(0, 8, "PEI \u2014 Autism.IA", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(8)
        self.set_draw_color(200, 220, 240)
        self.line(self.l_margin + 20, self.get_y(),
                  self.w - self.r_margin - 20, self.get_y())
        self.ln(8)

        self.set_font("DejaVu", "B", 13)
        self.set_text_color(50, 50, 50)
        self.cell(0, 8, f"Estudante: {self.student_name}", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("DejaVu", "", 11)
        self.cell(0, 7, f"Escola: {self.school}", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(self.h - 15)
        self.set_font("DejaVu", "I", 8)
        self.set_text_color(200, 220, 240)
        self.cell(0, 8, "Gerado por Autism.IA", align="C")

        self.set_auto_page_break(auto=True, margin=20)
        self.add_page()

    # ------------------------------------------------------------------
    # Renderizar Markdown
    # ------------------------------------------------------------------
    def render_markdown(self, text: str):
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]

            if line.strip().startswith("|"):
                table_lines = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i])
                    i += 1
                self._render_table(table_lines)
                continue

            stripped = line.strip()

            if stripped.startswith("# ") and not stripped.startswith("## "):
                self._section_title(stripped[2:].strip(), level=1)
            elif stripped.startswith("## ") and not stripped.startswith("### "):
                self._section_title(stripped[3:].strip(), level=2)
            elif stripped.startswith("### "):
                self._section_title(stripped[4:].strip(), level=3)
            elif _BULLET_RE.match(line):
                m = _BULLET_RE.match(line)
                self._bullet(_strip_bold(m.group(2)), sub=len(m.group(1)) > 0)
            elif _NUM_RE.match(line):
                m = _NUM_RE.match(line)
                self._bullet(_strip_bold(m.group(2)), symbol="\u2022",
                             sub=len(m.group(1)) > 0)
            elif re.match(r"^---+$", stripped):
                self.ln(2)
                self.set_draw_color(200, 200, 200)
                self.line(self.l_margin, self.get_y(),
                          self.w - self.r_margin, self.get_y())
                self.ln(4)
            elif stripped == "":
                self.ln(3)
            else:
                self._paragraph(stripped)

            i += 1

    # ------------------------------------------------------------------
    # Tabela — abordagem: calcular altura primeiro, depois desenhar
    # ------------------------------------------------------------------
    def _col_widths(self, n_cols: int) -> list:
        """Larguras proporcionais por número de colunas."""
        usable = self.w - self.l_margin - self.r_margin
        if n_cols == 1:
            return [usable]
        elif n_cols == 2:
            return [usable * p for p in [0.35, 0.65]]
        elif n_cols == 3:
            return [usable * p for p in [0.22, 0.40, 0.38]]
        elif n_cols == 4:
            return [usable * p for p in [0.20, 0.25, 0.28, 0.27]]
        else:
            return [usable / n_cols] * n_cols

    def _count_lines(self, text: str, col_w: float, bold: bool = False) -> int:
        """Conta quantas linhas o texto ocupará na célula."""
        self.set_font("DejaVu", "B" if bold else "", 8)
        inner = col_w - 4  # 2px padding cada lado
        if inner <= 0:
            return 1
        lines = 1
        x = 0.0
        for word in text.split():
            ww = self.get_string_width(word + " ")
            if x + ww > inner and x > 0:
                lines += 1
                x = ww
            else:
                x += ww
        return lines

    def _render_table(self, table_lines: list):
        rows = _parse_table(table_lines)
        if not rows:
            return

        n_cols = max(len(row) for row in rows)
        if n_cols == 0:
            return

        col_w = self._col_widths(n_cols)
        line_h = 5.2
        pad  = 2.0

        header_row = rows[0]

        self.ln(3)

        for r_idx, row in enumerate(rows):
            is_header = r_idx == 0

            # Calcular altura da linha
            max_lines = 1
            for c_idx in range(n_cols):
                cell_text = _strip_bold(row[c_idx] if c_idx < len(row) else "")
                n = self._count_lines(cell_text, col_w[c_idx], bold=is_header)
                max_lines = max(max_lines, n)
            row_h = max_lines * line_h + 2 * pad

            # Page break: se não couber, nova página e repete o cabeçalho
            if self.get_y() + row_h > self.h - self.b_margin:
                self.add_page()
                if not is_header:
                    self._draw_row(header_row, n_cols, col_w, line_h, pad,
                                   is_header=True, row_h=None)

            self._draw_row(row, n_cols, col_w, line_h, pad,
                           is_header=is_header, row_h=row_h)

        self.set_text_color(0, 0, 0)
        self.ln(4)

    def _draw_row(self, row: list, n_cols: int, col_w: list, line_h: float,
                  pad: float, is_header: bool, row_h):
        """Desenha uma linha da tabela com altura pré-calculada."""
        # Se row_h não fornecido, calcular agora
        if row_h is None:
            max_lines = 1
            for c_idx in range(n_cols):
                cell_text = _strip_bold(row[c_idx] if c_idx < len(row) else "")
                n = self._count_lines(cell_text, col_w[c_idx], bold=is_header)
                max_lines = max(max_lines, n)
            row_h = max_lines * line_h + 2 * pad

        x_start = self.l_margin
        y_start = self.get_y()

        # Cores
        if is_header:
            bg = (74, 144, 217)
            fg = (255, 255, 255)
            font_style = "B"
        else:
            # Índice real da linha de dados (r_idx não disponível aqui, usamos y_start)
            # Alternância detectada via cor de fundo: usando flag global não é prático,
            # então passamos sempre branco/azul claro via parâmetro externo
            bg = getattr(self, "_row_alt", (248, 251, 255))
            self._row_alt = (235, 243, 255) if bg == (248, 251, 255) else (248, 251, 255)
            fg = (30, 30, 30)
            font_style = ""

        # Desenhar fundo e borda de cada célula
        self.set_draw_color(180, 200, 230)
        for c_idx in range(n_cols):
            x = x_start + sum(col_w[:c_idx])
            self.set_fill_color(*bg)
            self.rect(x, y_start, col_w[c_idx], row_h, style="FD")

        # Escrever texto de cada célula
        for c_idx in range(n_cols):
            cell_text = _strip_bold(row[c_idx] if c_idx < len(row) else "")
            x = x_start + sum(col_w[:c_idx])
            self.set_xy(x + pad, y_start + pad)
            self.set_font("DejaVu", font_style, 8)
            self.set_text_color(*fg)
            self.multi_cell(col_w[c_idx] - 2 * pad, line_h, cell_text,
                            border=0, align="J", fill=False,
                            new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Avançar Y para o fim da linha
        self.set_y(y_start + row_h)

    # ------------------------------------------------------------------
    # Títulos de seção
    # ------------------------------------------------------------------
    def _section_title(self, text: str, level: int):
        self.ln(2)
        if level == 1:
            self.set_fill_color(74, 144, 217)
            self.set_text_color(255, 255, 255)
            self.set_font("DejaVu", "B", 13)
            self.set_x(self.l_margin)
            self.cell(self.w - self.l_margin - self.r_margin,
                      9, f"  {text}", fill=True,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(3)
        elif level == 2:
            self.set_text_color(30, 80, 160)
            self.set_font("DejaVu", "B", 11)
            self.multi_cell(0, 7, text, align="L",
                            new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_draw_color(74, 144, 217)
            self.line(self.l_margin, self.get_y(),
                      self.w - self.r_margin, self.get_y())
            self.ln(3)
        else:
            self.set_text_color(50, 50, 50)
            self.set_font("DejaVu", "B", 10)
            self.multi_cell(0, 6, text, align="L",
                            new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(1)
        self.set_text_color(0, 0, 0)

    def _bullet(self, text: str, symbol: str = "\u2013", sub: bool = False):
        self.set_font("DejaVu", "", 10)
        self.set_text_color(40, 40, 40)
        indent = 10 if sub else 5
        x = self.l_margin + indent
        available = self.w - x - self.r_margin - 6
        self.set_x(x)
        self.cell(6, 5, symbol)
        self.set_x(x + 6)
        self.multi_cell(available, 5, text, align="J",
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)
        self.set_text_color(0, 0, 0)

    def _paragraph(self, text: str):
        if not text:
            return
        text = re.sub(r"^\*\s+", "", text)
        if not text:
            return
        self.set_font("DejaVu", "", 10)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 5.5, _strip_bold(text), align="J",
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)
        self.set_text_color(0, 0, 0)


def markdown_to_pdf(markdown_text: str, student_name: str, school: str,
                    output_path: str) -> None:
    """Converte texto Markdown em PDF formatado e salva em output_path."""
    pdf = PEI_PDF(student_name=student_name, school=school)
    pdf.render_markdown(markdown_text)
    pdf.output(output_path)
