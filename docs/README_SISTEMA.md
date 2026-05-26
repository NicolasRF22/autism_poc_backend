# Autism.IA - Documento Consolidado do Sistema

Este documento consolida, em um só lugar, a visão geral do sistema Autism.IA, seus recursos principais, sua arquitetura atual, a organização do frontend e do backend, e o histórico das mudanças mais importantes que levaram ao estado atual da aplicação.

## 1. Visão geral

O Autism.IA é uma aplicação full-stack voltada ao gerenciamento educacional de alunos com autismo, com foco em apoio à elaboração de PEI, diário pedagógico, cadastro de entidades escolares e consulta assistida por IA.

O sistema combina quatro pilares principais:

1. Cadastro e gestão operacional de escolas, alunos, docentes e vínculos.
2. Registro pedagógico por meio de diário individual e PDI.
3. Geração e consulta assistida por RAG para apoiar PEI e chat contextual.
4. Controle de acesso por perfil, auditoria e trilha de ações para governança.

Na prática, a aplicação é organizada em um backend Flask com API REST, um frontend React/Vite e camadas de persistência para dados estruturados, documentos e vetores semânticos.

## 2. Objetivo do sistema

O objetivo do sistema é centralizar informações pedagógicas e administrativas relevantes para o acompanhamento de estudantes, permitindo que diferentes perfis de usuários atuem em escopos adequados ao seu papel.

Ele foi desenhado para:

- reduzir dispersão de informações entre formulários, arquivos e anotações isoladas;
- apoiar a produção de documentos educacionais personalizados;
- permitir acesso segmentado por perfil, escola ou município;
- manter histórico de ações e transparência operacional;
- usar IA de forma controlada, baseada em documentos reais e contexto recuperado.

## 3. O que o sistema contém

O sistema reúne os seguintes blocos funcionais:

- autenticação e autorização por perfil;
- cadastro de escolas;
- cadastro de alunos;
- cadastro de docentes;
- diário individual por aluno;
- PDI por aluno;
- PEI gerado com apoio de RAG;
- chat contextual com base em documentos carregados;
- upload e indexação de PDFs;
- armazenamento remoto de arquivos;
- formulários e submissões;
- módulo de municípios;
- auditoria de eventos;
- métricas de uso da IA;
- interface de navegação e operação por perfis.

## 4. Arquitetura atual

A arquitetura atual consolidou três camadas de persistência e uma camada de aplicação:

- backend Flask como camada de API e orquestração;
- Supabase Postgres como fonte de verdade para dados estruturados;
- ChromaDB para vetores e busca semântica do RAG;
- Supabase Storage para arquivos PDF e anexos privados.

### 4.1 Backend

O backend expõe a API REST e concentra as regras de autorização, auditoria, persistência e integração com IA.

Os domínios principais ficam agrupados em rotas como:

- autenticação e usuários;
- auditoria;
- escolas;
- alunos;
- docentes;
- diário;
- PDI;
- RAG;
- formulários e submissões;
- administração e uso de IA.

### 4.2 Persistência estruturada

Os dados estruturados passaram a ser armazenados no Postgres por meio de repositórios SQLAlchemy. Isso abrange os principais registros operacionais do sistema, como escolas, alunos, docentes, diários, PDI, submissões e metadados de objetos armazenados.

### 4.3 Persistência vetorial

O ChromaDB guarda chunks de texto e embeddings dos documentos usados pelo RAG. Ele é responsável por permitir busca por similaridade semântica, em vez de apenas correspondência literal de palavras.

### 4.4 Armazenamento de arquivos

Os PDFs originais e os documentos gerados ficam armazenados em buckets privados do Supabase Storage. O Postgres mantém os metadados de cada objeto para rastrear nome original, bucket, chave, tipo e referência de domínio.

## 5. Recursos por domínio

### 5.1 Autenticação e autorização

O sistema usa JWT no backend e RBAC para controlar o acesso às rotas e aos dados. Os perfis suportados incluem:

- admin;
- secretaria;
- coordenacao;
- professor;
- viewer.

O usuário autenticado recebe acesso de acordo com seu perfil e com o escopo associado, como município, escola ou vínculo docente.

O módulo também mantém:

- login;
- obtenção do usuário autenticado;
- logout stateless no cliente;
- criação e atualização de usuários por admin;
- leitura da auditoria por admin.

### 5.2 Escolas

O módulo de escolas permite criar, consultar, atualizar e remover registros de instituições, além de sustentar vínculos com alunos e outros dados operacionais.

Esse cadastro é parte central do sistema porque serve de base para:

- escopo de acesso;
- agrupamento de alunos;
- associação com docentes;
- organização de diário, PDI e PEI.

### 5.3 Alunos

O cadastro de alunos concentra os registros educacionais e o vínculo com escola, município e demais entidades relacionadas.

Os dados de aluno são usados em:

- diário;
- PDI;
- PEI;
- anexos;
- geração de contexto para RAG;
- filtros por escopo de acesso.

### 5.4 Docentes

O módulo de docentes registra os profissionais vinculados às escolas e sustenta o escopo de edição do professor, especialmente em diário e PDI.

### 5.5 Diário individual

O diário registra observações e acompanhamento pedagógico individualizado por aluno.

Esse módulo foi validado com persistência em modos distintos durante a evolução do sistema e hoje faz parte do conjunto consolidado de dados estruturados da aplicação.

### 5.6 PDI

O PDI armazena o plano individualizado de desenvolvimento do aluno.

Ele participa do fluxo pedagógico central e foi tratado como um domínio separado, com suporte a operações completas de criação, leitura, atualização e exclusão.

### 5.7 PEI com RAG

O PEI é gerado com apoio de Retrieval-Augmented Generation.

O fluxo segue este princípio:

1. o sistema recebe documentos relevantes do aluno;
2. o texto é extraído e dividido em chunks;
3. são criados embeddings;
4. os vetores são indexados no ChromaDB;
5. uma consulta recupera os trechos semanticamente mais próximos;
6. o modelo de IA gera a resposta ou o PEI com base no contexto recuperado.

Esse desenho evita respostas inventadas e força a geração a partir de documentos reais.

### 5.8 Chat contextual

O chat usa a mesma base de RAG para responder perguntas com base nos documentos indexados.

O sistema recupera trechos relevantes, mantém contexto de conversa quando aplicável e devolve a resposta com base em evidências recuperadas.

### 5.9 Upload, anexos e documentos PDF

O sistema suporta upload e download de PDFs associados a documentos do domínio educacional.

Isso inclui:

- anexos por aluno;
- PDFs indexados para RAG;
- PDFs gerados de PEI;
- armazenamento privado em buckets remotos.

### 5.10 Formulários e submissões

Além dos cadastros principais, o sistema também contempla fluxos de formulário e submissão, como pré-cadastros e processos relacionados ao registro escolar.

Esse bloco é importante porque amplia o sistema para além do CRUD básico e mostra uma camada de entrada de dados estruturados.

### 5.11 Municípios

O módulo de municípios existe para sustentar o escopo administrativo e o acesso por território, especialmente no perfil de secretaria.

### 5.12 Auditoria

As ações relevantes são registradas em trilha de auditoria append-only.

A auditoria cobre, entre outros pontos:

- requisições mutáveis;
- downloads;
- geração ou acesso a PDFs;
- login e logout.

Isso cria um histórico de comportamento importante para controle operacional e rastreabilidade.

### 5.13 Métricas de IA

O sistema também acompanha o uso de modelos de IA, com visão de consumo por janela de tempo, operação e limites configurados.

Isso ajuda a controlar custo, volume e limites de uso em produção.

## 6. Frontend

O frontend é construído com React e Vite, e organiza a navegação conforme o perfil do usuário.

Os pontos mais importantes do frontend são:

- bootstrap da sessão ao abrir a aplicação;
- proteção de rotas;
- persistência do token no cliente;
- inclusão automática do token nas requisições;
- menu lateral adaptado ao perfil;
- páginas específicas para os fluxos operacionais do sistema.

Na prática, o frontend não apenas consome a API: ele também modela a experiência por papel, expondo ou escondendo recursos conforme o usuário autenticado.

## 7. Fluxos principais da aplicação

### 7.1 Fluxo de cadastro

O usuário autenticado cria ou atualiza entidades como escola, aluno e docente, conforme seu perfil e escopo.

### 7.2 Fluxo pedagógico

O fluxo pedagógico conecta cadastro, diário, PDI e PEI.

O sistema parte do aluno e da escola para registrar o acompanhamento cotidiano e, quando necessário, usar os documentos disponíveis para gerar ou apoiar documentos mais completos.

### 7.3 Fluxo de documentos e RAG

Os arquivos PDF são enviados, processados, indexados e depois usados como base para chat e geração de PEI.

Esse fluxo é o coração da parte de IA do sistema.

### 7.4 Fluxo de governança

Autenticação, RBAC, auditoria e métricas de IA compõem a camada de governança.

Esse conjunto protege o uso da plataforma e ajuda a manter rastreabilidade das ações.

## 8. Como as mudanças foram feitas ao longo do tempo

O sistema passou por uma evolução documentada em fases, com validação incremental e mudança de arquitetura de persistência.

### 8.1 Fase 1

A primeira fase validou os domínios de escolas, alunos e docentes em três modos de operação:

- file;
- postgres;
- dual.

Essa etapa confirmou que o sistema podia operar tanto com persistência local quanto com Postgres, e também em modo híbrido durante a transição.

### 8.2 Fase 2

A segunda fase validou diary e PDI nos mesmos modos de operação:

- file;
- postgres;
- dual.

Isso consolidou a migração dos domínios centrais para a camada relacional, sem perder compatibilidade com o fluxo anterior durante a transição.

### 8.3 Consolidação da arquitetura atual

Com o avanço das fases, a aplicação passou a tratar o Postgres como fonte de verdade para dados estruturados, o ChromaDB para busca vetorial e o Supabase Storage para arquivos.

O modelo local em JSON permaneceu como referência histórica e compatibilidade em alguns pontos, mas deixou de ser a base principal da arquitetura atual.

### 8.4 O que mudou na prática

As mudanças mais relevantes foram:

- separação entre persistência de dados estruturados, vetores e arquivos;
- uso de repositórios para isolar acesso ao banco;
- reforço de autenticação e autorização;
- auditoria append-only;
- padronização dos fluxos de RAG;
- organização de scripts de smoke test e validação por fase.

## 9. Tecnologias usadas

- Backend: Python 3.12 + Flask.
- Frontend: React + Vite.
- Banco relacional: Supabase Postgres.
- Busca vetorial: ChromaDB.
- Object storage: Supabase Storage.
- IA generativa: Google Gemini.
- Embeddings: modelo de embeddings do Gemini.
- Autenticação: JWT.
- Auditoria: JSONL append-only.

## 10. Estrutura lógica do repositório

O backend concentra o núcleo da aplicação e a documentação técnica principal. O frontend contém a interface de operação e navegação por perfil.

Principais áreas de interesse:

- backend app.py: orquestração da API;
- backend postgres_repositories.py: persistência relacional;
- backend auth_storage.py: usuários e permissões;
- backend audit_storage.py: auditoria;
- backend rag_engine.py: geração e chat com IA;
- backend vector_store.py: abstração do ChromaDB;
- backend document_processor.py: extração e preparação de documentos;
- frontend App.jsx: rotas e proteção;
- frontend Sidebar.jsx: navegação por perfil;
- frontend services/api.js: cliente HTTP e sessão.

## 11. Pontos importantes para manutenção

Ao evoluir o sistema, é importante preservar alguns princípios:

- separar com clareza o que é legado do que é arquitetura atual;
- manter o escopo de acesso por perfil e vínculo;
- garantir que RAG sempre use documentos reais recuperados;
- manter auditoria ativa em ações relevantes;
- preservar compatibilidade entre frontend e payloads da API quando houver migrações;
- validar mudanças com smoke tests por domínio quando houver alteração de persistência ou comportamento.

## 12. Resumo final

O Autism.IA é mais do que um cadastro escolar. Ele é uma plataforma integrada para acompanhamento pedagógico, geração assistida de documentos e organização operacional com controle de acesso, auditoria e armazenamento estruturado.

Seu estado atual combina:

- backend Flask como núcleo da API;
- Postgres como banco principal;
- ChromaDB para busca semântica;
- Supabase Storage para arquivos;
- frontend React/Vite com navegação por perfil;
- autenticação JWT com RBAC;
- histórico documentado de evolução por fases.

Em termos práticos, o sistema foi construído para centralizar a operação, dar suporte a decisões pedagógicas e permitir uso de IA com base em evidências reais, sem perder rastreabilidade nem organização entre módulos.
