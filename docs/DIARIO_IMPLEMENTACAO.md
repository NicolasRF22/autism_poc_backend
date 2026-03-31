# Implementação do Diário de Acompanhamento Individual

**Data de Implementação:** 01 de Março de 2026

## 📋 Visão Geral

Sistema completo para registro diário de atividades e comportamentos de alunos com autismo, permitindo acompanhamento longitudinal por múltiplos professores ao longo do ano letivo.

## 🎯 Funcionalidades Implementadas

- ✅ Armazenamento persistente de registros diários
- ✅ Suporte a múltiplos professores responsáveis por registro
- ✅ Sistema de memória de professores (último professor usado aparece como padrão)
- ✅ Histórico completo de entradas por aluno
- ✅ 7 perguntas padronizadas com 3 opções de resposta (Sim/Parcialmente/Não)
- ✅ Campo aberto para observações comportamentais
- ✅ Interface de listagem e navegação por aluno
- ✅ Exclusão de entradas com confirmação

## 🆕 Atualização (23/03/2026) — Importação de Diário por PDF (sem IA)

Foi implementado um fluxo de importação determinística de PDF para Diário com revisão humana antes do salvamento.

### Backend

- Novo parser: `backend/diary_pdf_parser.py`
   - Extração de texto pesquisável via `PyPDF2`
   - Split por dia letivo detectando datas no texto
   - Parsing por regras (regex) para perguntas do Diário
   - Fallback sem OCR: cria rascunho vazio quando o PDF não tem texto extraível

- Novas rotas em `backend/app.py`
   - `POST /api/diary/import/preview`
      - Recebe PDF e retorna entradas em modo preview (não persiste)
      - Resolve aluno por `student_id` (prioritário) ou `student_name`
      - Inclui avisos de parsing e aviso de possível duplicidade (mesmo aluno+data)
   - `POST /api/diary/import/commit`
      - Persiste entradas revisadas no JSON do Diário
      - Suporta status `draft` e `final`
      - Permite duplicidade com aviso (não bloqueia)

- Evolução de schema em `backend/diary_storage.py`
   - Novos campos por entrada:
      - `student_id` (referência principal)
      - `status` (`draft` ou `final`)
      - `source` (`manual` ou `pdf_import`)
      - `parse_warnings` (lista de avisos)
      - `updated_at`
   - Compatibilidade preservada com entradas antigas.

### Frontend

- `frontend/src/pages/DiaryPage.jsx`
   - Botão `Importar PDF`
   - Modal com:
      - Upload do arquivo
      - Geração de preview
      - Edição manual de aluno/data/professores/respostas/observações/status
      - Exibição de avisos por entrada
      - Confirmação de importação

- `frontend/src/services/api.js`
   - Métodos novos:
      - `diaryAPI.previewPdfImport(file, options)`
      - `diaryAPI.commitPdfImport(entries)`

### Observações operacionais

- Sem OCR por decisão de escopo.
- Para PDFs não pesquisáveis, o fluxo cria rascunho para preenchimento manual.
- O JSON continua como formato canônico de armazenamento, adequado para pipeline posterior de RAG e busca semântica.

### OCR (atualização)

O parser de importação passou a suportar OCR com fallback automático.

- Ordem de tentativa:
   1) Texto nativo do PDF
   2) OCR com Tesseract (quando habilitado)
   3) Escolha automática da melhor saída por score de qualidade
- Endpoint `POST /api/diary/import/preview` aceita:
   - `use_ocr` (`true|false`)
   - `ocr_lang` (padrão `por`)
   - `ocr_force` (`true|false`)

Dependências Python:

- `pytesseract`
- `pypdfium2`
- `Pillow`

Dependência de sistema (WSL/Linux):

- `tesseract-ocr`
- `tesseract-ocr-por` (recomendado para português)

Se o pacote de idioma `por` não estiver disponível, o parser tenta fallback em `eng` e registra aviso em `warnings`.

---

## 🗂️ Estrutura de Arquivos

### Backend (Python/Flask)

#### 1. **backend/diary_storage.py** (Novo arquivo)
Sistema de armazenamento persistente baseado em JSON, seguindo o padrão do `pei_storage.py`.

**Classe Principal:** `DiaryStorage`

**Métodos Implementados:**
```python
- save_entry()           # Salva nova entrada de diário
- list_all_students()    # Lista alunos únicos
- get_entries_by_student() # Busca entradas de um aluno
- get_entry()           # Busca entrada específica por ID
- delete_entry()        # Remove entrada
- get_last_teachers()   # Retorna professores da última entrada
- get_student_summary() # Resumo de um aluno
- list_all_summaries()  # Resumos de todos os alunos
```

**Estrutura de Dados (JSON):**
```json
{
  "id": "uuid-v4",
  "student_name": "Nome do Aluno",
  "teachers": ["Prof. Maria", "Prof. João"],
  "diary_date": "2026-03-01",
  "answers": {
    "lanchou": "Sim",
    "participou_brincadeira": "Parcialmente",
    "atencao_professora": "Sim",
    "interesse_atividades": "Sim",
    "realizou_atividades": "Parcialmente",
    "uso_banheiro": "Sim",
    "cumpriu_combinados": "Não"
  },
  "open_obs": "Aluno apresentou birra durante atividade de pintura...",
  "created_at": "2026-03-01T14:30:00"
}
```

**Armazenamento:** `backend/diaries/index.json`

#### 2. **backend/app.py** (Modificado)
Adicionadas 6 novas rotas REST para o diário.

**Importações Adicionadas:**
```python
from diary_storage import DiaryStorage

DIARIES_FOLDER = os.path.join(os.path.dirname(__file__), 'diaries')
_diary_storage = DiaryStorage(storage_dir=DIARIES_FOLDER)
```

**Rotas da API:**

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/diary/students` | Lista todos os alunos com resumos |
| GET | `/api/diary/entries/<student_name>` | Busca entradas de um aluno |
| POST | `/api/diary/entries` | Cria nova entrada de diário |
| GET | `/api/diary/entries/<entry_id>` | Busca entrada específica |
| DELETE | `/api/diary/entries/<entry_id>` | Remove entrada |
| GET | `/api/diary/last-teachers/<student_name>` | Retorna últimos professores |

**Exemplo de Requisição POST:**
```json
POST /api/diary/entries
{
  "student_name": "João Silva",
  "teachers": ["Profa. Maria Santos", "Prof. Carlos Lima"],
  "diary_date": "2026-03-01",
  "answers": {
    "lanchou": "Sim",
    "participou_brincadeira": "Sim",
    "atencao_professora": "Parcialmente",
    "interesse_atividades": "Sim",
    "realizou_atividades": "Sim",
    "uso_banheiro": "Sim",
    "cumpriu_combinados": "Sim"
  },
  "open_obs": "Dia tranquilo, boa participação."
}
```

---

### Frontend (React)

#### 3. **frontend/src/pages/DiaryPage.jsx** (Novo arquivo)
Página principal de gerenciamento de diários.

**Componente:** `DiaryPage`

**Estados:**
```javascript
- students          // Lista de alunos com resumos
- selectedStudent   // Aluno selecionado para ver histórico
- studentEntries    // Entradas do aluno selecionado
- showNewDiaryModal // Controle do modal de criação
```

**Funcionalidades:**
- Lista em cards todos os alunos com diários
- Exibe resumo: última data, professores, total de registros
- Modal para criar novo diário (solicita nome do aluno)
- Visualização de histórico completo por aluno
- Exclusão de entradas com confirmação

**Fluxo de Navegação:**
1. Tela inicial: Grid com cards de alunos
2. Clique no card → Histórico de entradas do aluno
3. Botão "Nova Entrada" → Navega para formulário
4. Botão "Novo Diário" → Modal para criar diário de novo aluno

#### 4. **frontend/src/pages/DiaryPage.css** (Novo arquivo)
Estilos completos para a página de diários.

**Principais Classes:**
- `.diary-page` - Container principal
- `.students-grid` - Grid responsivo de cards
- `.student-card` - Card de aluno com hover effect
- `.entry-card` - Card de entrada com histórico
- `.answer-badge` - Badge colorido por resposta (verde/amarelo/vermelho)
- `.modal-overlay` - Modal de criação de diário

#### 5. **frontend/src/pages/DiaryEntry.jsx** (Novo arquivo)
Formulário de entrada de diário.

**Componente:** `DiaryEntry`

**Parâmetros de Rota:**
- `studentName` - Nome do aluno (via URL)

**Estados:**
```javascript
- teachers      // Array de professores
- teacherInput  // Input temporário para adicionar professor
- diaryDate     // Data do registro (padrão: hoje)
- answers       // Objeto com respostas das 7 perguntas
- openObs       // Observações abertas
```

**Seções do Formulário:**

1. **Cabeçalho de Informações:**
   - Aluno (desabilitado, vem da URL)
   - Professor(es) - Sistema de tags para múltiplos professores
   - Dia Letivo - Date picker

2. **Perguntas de Atividade (7 perguntas):**
   - Lanchou?
   - Participou da brincadeira/atividade coletiva?
   - Deu atenção à fala da professora?
   - Demonstrou interesse para as atividades?
   - Realizou as atividades propostas?
   - Fez uso do banheiro?
   - Cumpriu os combinados?
   
   **Opções:** Sim | Parcialmente | Não (botões visuais)

3. **Observações Abertas:**
   - Textarea para registrar crises, birras ou comportamentos distintos

**Validações:**
- Pelo menos 1 professor obrigatório
- Data obrigatória
- Todas as 7 perguntas devem ser respondidas

**Funcionalidade de Memória:**
- Ao carregar, busca automaticamente os professores da última entrada do aluno
- Se encontrados, preenche automaticamente o campo de professores
- Permite edição/remoção/adição de novos professores

#### 6. **frontend/src/pages/DiaryEntry.css** (Novo arquivo)
Estilos do formulário de entrada.

**Destaques:**
- `.option-button` - Botões de resposta com estados visuais
- `.selected.sim` - Verde (positivo)
- `.selected.parcialmente` - Amarelo (neutro)
- `.selected.não` - Vermelho (negativo)
- `.teachers-tags` - Sistema de chips para professores
- Responsivo para mobile

#### 7. **frontend/src/components/Sidebar.jsx** (Modificado)
Adicionado item de menu para o diário.

**Alteração:**
```javascript
const menuItems = [
  { path: '/', label: 'Início', icon: '🏠' },
  { path: '/formularios', label: 'Formulários', icon: '📋' },
  { path: '/respostas', label: 'Respostas', icon: '📊' },
  { path: '/diario', label: 'Diário Individual', icon: '📖' },  // NOVO
  { path: '/teste-rag', label: 'Teste RAG', icon: '🤖' },
];
```

#### 8. **frontend/src/App.jsx** (Modificado)
Adicionadas rotas para as páginas do diário.

**Importações:**
```javascript
import DiaryPage from './pages/DiaryPage';
import DiaryEntry from './pages/DiaryEntry';
```

**Rotas Adicionadas:**
```javascript
<Route path="/diario" element={<DiaryPage />} />
<Route path="/diario/:studentName/novo" element={<DiaryEntry />} />
```

#### 9. **frontend/src/services/api.js** (Modificado)
Adicionado módulo `diaryAPI` com funções para comunicação com backend.

**Novo Módulo:**
```javascript
export const diaryAPI = {
  getStudents: async () => {...},           // Lista alunos
  getStudentEntries: async (name) => {...}, // Busca entradas
  createEntry: async (data) => {...},       // Cria entrada
  getEntry: async (id) => {...},            // Busca entrada
  deleteEntry: async (id) => {...},         // Remove entrada
  getLastTeachers: async (name) => {...}    // Busca últimos profs
};
```

---

## 🔄 Fluxo de Funcionamento

### Criação de Novo Diário

```
1. Usuário clica em "Diário Individual" na sidebar
   ↓
2. DiaryPage carrega lista de alunos (GET /api/diary/students)
   ↓
3. Usuário clica em "+ Novo Diário"
   ↓
4. Modal solicita nome do aluno
   ↓
5. Navegação para /diario/{aluno}/novo
   ↓
6. DiaryEntry carrega (tenta buscar professores anteriores)
   ↓
7. Usuário preenche professores, data, 7 perguntas e observações
   ↓
8. Submit → POST /api/diary/entries
   ↓
9. DiaryStorage salva em backend/diaries/index.json
   ↓
10. Navegação de volta para /diario
```

### Continuação de Diário Existente

```
1. DiaryPage exibe cards de alunos
   ↓
2. Usuário clica no card do aluno
   ↓
3. GET /api/diary/entries/{aluno}
   ↓
4. Exibe histórico de entradas
   ↓
5. Usuário clica em "Nova Entrada"
   ↓
6. DiaryEntry pré-preenche professores da última entrada
   ↓
7. Processo de criação continua...
```

### Visualização de Histórico

```
1. DiaryPage → Click no card do aluno
   ↓
2. GET /api/diary/entries/{aluno}
   ↓
3. Exibe lista de entradas ordenadas por data (desc)
   ↓
4. Cada entrada mostra:
   - Data do registro
   - Professor(es)
   - Respostas das 7 perguntas (badges coloridos)
   - Observações abertas
   - Botão de exclusão
```

---

## 🎨 Design e UX

### Paleta de Cores

- **Primary:** `#667eea` (Roxo)
- **Success:** `#27ae60` (Verde) - Resposta "Sim"
- **Warning:** `#f39c12` (Amarelo) - Resposta "Parcialmente"
- **Danger:** `#e74c3c` (Vermelho) - Resposta "Não"
- **Text Primary:** `#2c3e50`
- **Background:** `#f8f9fa`

### Componentes Visuais

1. **Cards de Aluno:**
   - Ícone de usuário 👤
   - Nome do aluno em destaque
   - Informações resumidas
   - Hover effect com elevação

2. **Badges de Resposta:**
   - Cor de fundo baseada na resposta
   - Texto em maiúsculas
   - Bordas arredondadas

3. **Tags de Professores:**
   - Chips roxos removíveis
   - Botão × para remover
   - Input inline para adicionar

4. **Botões de Resposta:**
   - 3 botões lado a lado
   - Estado selecionado com gradiente
   - Efeito de elevação no hover

---

## 📊 Estrutura de Dados

### Arquivo: `backend/diaries/index.json`

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "student_name": "João Silva",
    "teachers": ["Profa. Maria Santos", "Prof. Carlos Lima"],
    "diary_date": "2026-03-01",
    "answers": {
      "lanchou": "Sim",
      "participou_brincadeira": "Sim",
      "atencao_professora": "Parcialmente",
      "interesse_atividades": "Sim",
      "realizou_atividades": "Sim",
      "uso_banheiro": "Sim",
      "cumpriu_combinados": "Não"
    },
    "open_obs": "Apresentou dificuldade em seguir os combinados após o recreio.",
    "created_at": "2026-03-01T14:30:25.123456"
  },
  {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "student_name": "João Silva",
    "teachers": ["Profa. Maria Santos"],
    "diary_date": "2026-03-02",
    "answers": {
      "lanchou": "Sim",
      "participou_brincadeira": "Sim",
      "atencao_professora": "Sim",
      "interesse_atividades": "Sim",
      "realizou_atividades": "Sim",
      "uso_banheiro": "Sim",
      "cumpriu_combinados": "Sim"
    },
    "open_obs": "Dia excelente, grande evolução!",
    "created_at": "2026-03-02T15:12:08.987654"
  }
]
```

---

## 🚀 Como Executar

### Backend

```bash
# Ativar ambiente virtual
cd /home/nicolas/Aut
source ~/.virtualenvs/autismia-dotvenv/bin/activate

# Instalar dependências (se necessário)
pip install -r backend/requirements.txt

# Iniciar servidor
cd backend
python app.py

# Servidor disponível em: http://localhost:5000
```

### Frontend

```bash
# Instalar dependências (primeira vez)
cd /home/nicolas/Aut/frontend
npm install

# Iniciar servidor de desenvolvimento
npm run dev

# Interface disponível em: http://localhost:3000
```

---

## 🧪 Testes Realizados

### Backend
- ✅ Rota `/api/health` - Servidor funcionando
- ✅ Rota `/api/diary/students` - Retorna array vazio inicialmente
- ✅ Rotas criadas e respondendo corretamente
- ✅ DiaryStorage inicializa pasta `diaries/`

### Frontend
- ✅ Build sem erros
- ✅ Rotas configuradas corretamente
- ✅ Navegação funcionando
- ✅ Componentes renderizando

---

## 📝 Perguntas do Formulário

1. **Lanchou?** - Verifica se o aluno se alimentou no horário do lanche
2. **Participou da brincadeira/atividade coletiva?** - Avalia socialização
3. **Deu atenção à fala da professora?** - Mede atenção e foco
4. **Demonstrou interesse para as atividades?** - Engajamento geral
5. **Realizou as atividades propostas?** - Conclusão de tarefas
6. **Fez uso do banheiro?** - Autonomia e rotina
7. **Cumpriu os combinados?** - Seguimento de regras

**Opções de Resposta:** Sim | Parcialmente | Não

**Campo Adicional:** Observações abertas para registrar crises, birras ou comportamentos atípicos.

---

## 🔧 Tecnologias Utilizadas

### Backend
- **Flask 3.0.0** - Framework web
- **Python 3.12** - Linguagem
- **orjson** - Serialização JSON rápida
- **uuid** - Geração de IDs únicos
- **datetime** - Timestamps

### Frontend
- **React 18** - Biblioteca UI
- **React Router 6** - Roteamento
- **Vite** - Build tool
- **CSS3** - Estilização
- **Fetch API** - Requisições HTTP

---

## 📌 Decisões Técnicas

1. **Armazenamento em JSON vs Banco de Dados:**
   - Escolhido JSON para simplicidade e consistência com PEIStorage
   - Adequado para volume moderado de dados
   - Migração para BD facilitada pela camada de abstração

2. **Múltiplos Professores:**
   - Implementado como array de strings
   - Permite flexibilidade (troca de professor, co-docência)
   - UI com chips/tags intuitiva

3. **Memória de Professores:**
   - Melhora UX ao pré-preencher professores usuais
   - Reduz trabalho repetitivo
   - Mantém flexibilidade de edição

4. **3 Opções de Resposta:**
   - "Sim/Parcialmente/Não" oferece mais nuances que boolean
   - Captura comportamentos intermediários
   - Interface visual clara com cores

5. **Separação de Rotas:**
   - `/diario` - Lista/histórico
   - `/diario/:nome/novo` - Formulário de entrada
   - Navegação clara e RESTful

---

## 🎯 Possíveis Melhorias Futuras

- [ ] Filtros por período (últimos 7/30 dias)
- [ ] Gráficos de evolução por pergunta
- [ ] Exportação de relatório em PDF
- [ ] Comparação entre alunos (dashboards)
- [ ] Notificações para professores
- [ ] Anexo de fotos/vídeos nas observações
- [ ] Integração com sistema RAG para análise de padrões
- [ ] Sugestões automáticas de intervenções baseadas em histórico

---

## 📄 Arquivos de Configuração

Nenhuma alteração necessária em:
- `requirements.txt` - Dependências já instaladas
- `.env` - Sem novas variáveis de ambiente
- `vite.config.js` - Configuração mantida
- `package.json` - Sem novas dependências

---

## ✅ Checklist de Implementação

- [x] Backend: Sistema de armazenamento
- [x] Backend: Rotas da API
- [x] Frontend: Página de listagem
- [x] Frontend: Formulário de entrada
- [x] Frontend: Estilos e CSS
- [x] Integração: Sidebar e rotas
- [x] Integração: Funções de API
- [x] Testes: Backend funcionando
- [x] Testes: Frontend funcionando
- [x] Documentação: README atualizado

---

## 👥 Casos de Uso

### Professor Regular
1. Acessa o sistema diariamente
2. Seleciona aluno existente
3. Preenche registro rápido (professores já pré-selecionados)
4. Salva e continua para próximo aluno

### Professor Substituto
1. Acessa o sistema
2. Seleciona aluno
3. Remove professor anterior
4. Adiciona seu nome
5. Preenche registro

### Coordenador Pedagógico
1. Acessa histórico de aluno
2. Visualiza evolução ao longo do tempo
3. Identifica padrões em observações
4. Planeja intervenções

---

## 🐛 Troubleshooting

### Backend não inicia
```bash
# Verificar se porta 5000 está ocupada
lsof -ti:5000 | xargs kill -9

# Ativar venv
source ~/.virtualenvs/autismia-dotvenv/bin/activate

# Reinstalar dependências
pip install -r backend/requirements.txt
```

### Frontend com erro de rota
- Verificar se backend está rodando
- Conferir URL da API em `api.js` (localhost:5000)
- Limpar cache do navegador

### Dados não persistem
- Verificar se pasta `backend/diaries/` foi criada
- Verificar permissões de escrita
- Checar logs do backend para erros

---

**Implementado com sucesso em 01/03/2026** 🎉
