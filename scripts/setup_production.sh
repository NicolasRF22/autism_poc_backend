#!/bin/bash

# Script de Setup Rápido - Autism.IA
# Execute com: bash backend/scripts/setup_production.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$BASE_DIR/backend"
FRONTEND_DIR="$BASE_DIR/frontend"
BACKEND_ENV="$BACKEND_DIR/.env"
BACKEND_ENV_EXAMPLE="$BACKEND_DIR/.env.example"

echo "🚀 Configurando Autism.IA para Produção"
echo "========================================"
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verificar se .env existe
if [ ! -f "$BACKEND_ENV" ]; then
    echo -e "${YELLOW}⚠️  Arquivo .env não encontrado. Criando...${NC}"
    cp "$BACKEND_ENV_EXAMPLE" "$BACKEND_ENV"
else
    echo -e "${GREEN}✓ Arquivo .env encontrado${NC}"
fi

# Verificar GOOGLE_API_KEY
GOOGLE_KEY=$(grep "^GOOGLE_API_KEY=" "$BACKEND_ENV" | cut -d'=' -f2)
if [ "$GOOGLE_KEY" == "YOUR_GOOGLE_API_KEY_HERE" ] || [ -z "$GOOGLE_KEY" ]; then
    echo -e "${RED}❌ GOOGLE_API_KEY não configurada!${NC}"
    echo "Por favor, obtenha sua chave em: https://aistudio.google.com/app/apikey"
    read -p "Cole sua GOOGLE_API_KEY aqui: " USER_API_KEY
    sed -i "s|GOOGLE_API_KEY=.*|GOOGLE_API_KEY=$USER_API_KEY|g" "$BACKEND_ENV"
    echo -e "${GREEN}✓ GOOGLE_API_KEY salva no .env${NC}"
else
    echo -e "${GREEN}✓ GOOGLE_API_KEY já configurada${NC}"
fi

# Configurar DEBUG=False
sed -i 's|DEBUG=True|DEBUG=False|g' "$BACKEND_ENV"
echo -e "${GREEN}✓ DEBUG=False configurado para produção${NC}"

# Solicitar IP do servidor
echo ""
echo "🌐 Configuração do Frontend"
echo "---------------------------"
read -p "Digite o IP ou domínio do seu servidor (ex: 123.45.67.89): " SERVER_IP

if [ -z "$SERVER_IP" ]; then
    echo -e "${YELLOW}⚠️  IP não fornecido. Você precisará configurar manualmente.${NC}"
else
    # Criar .env para o frontend
    echo "VITE_API_BASE_URL=http://$SERVER_IP:5000/api" > "$FRONTEND_DIR/.env"
    echo -e "${GREEN}✓ Frontend configurado para usar: http://$SERVER_IP:5000/api${NC}"
fi

echo ""
echo "📦 Instalando dependências..."
echo "-----------------------------"

# Backend
echo "Backend..."
pip install -r "$BACKEND_DIR/requirements.txt" > /dev/null 2>&1
echo -e "${GREEN}✓ Dependências do backend instaladas${NC}"

# Frontend
echo "Frontend..."
cd "$FRONTEND_DIR"
npm install > /dev/null 2>&1
echo -e "${GREEN}✓ Dependências do frontend instaladas${NC}"
cd "$BASE_DIR"

echo ""
echo "🎉 Configuração concluída!"
echo "========================="
echo ""
echo "Para iniciar a aplicação:"
echo ""
echo "1. Backend:"
echo "   cd $BACKEND_DIR && python app.py"
echo ""
echo "2. Frontend (em outro terminal):"
echo "   cd $FRONTEND_DIR && npm run build && npx serve -s dist -l 3000"
echo ""
echo "3. Acesse: http://$SERVER_IP:3000"
echo ""
echo "⚠️  IMPORTANTE: Leia o arquivo DEPLOYMENT_GUIDE.md para:"
echo "   - Configurar Nginx (recomendado)"
echo "   - Configurar HTTPS"
echo "   - Usar PM2 para manter a aplicação rodando"
echo "   - Local do guia: $BACKEND_DIR/docs/DEPLOYMENT_GUIDE.md"
echo ""
