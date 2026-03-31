#!/bin/bash

# Script para iniciar Backend e Frontend simultaneamente

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$BASE_DIR/backend"
FRONTEND_DIR="$BASE_DIR/frontend"
VENV_CANDIDATES=(
	"$BASE_DIR/.venv"
	"$BASE_DIR/venv"
	"$HOME/.virtualenvs/autismia-dotvenv"
	"$HOME/.virtualenvs/autismia-venv"
)

echo "🚀 Iniciando Autism.IA..."
echo ""

# Ativar ambiente virtual Python
echo "📦 Ativando ambiente virtual Python..."
VENV_ACTIVATED=false
for candidate in "${VENV_CANDIDATES[@]}"; do
	if [ -f "$candidate/bin/activate" ]; then
		source "$candidate/bin/activate"
		VENV_ACTIVATED=true
		break
	fi
done

if [ "$VENV_ACTIVATED" != "true" ]; then
	echo "❌ Ambiente virtual não encontrado (raiz do projeto ou ~/.virtualenvs)."
	exit 1
fi

# Iniciar backend em segundo plano
echo "🐍 Iniciando Backend (Flask)..."
cd "$BACKEND_DIR"
python app.py &
BACKEND_PID=$!

# Aguardar backend iniciar
sleep 3

# Iniciar frontend
echo "⚛️  Iniciando Frontend (React)..."
cd "$FRONTEND_DIR"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Aplicação iniciada!"
echo ""
echo "📍 Backend: http://localhost:5000"
echo "📍 Frontend: http://localhost:3000"
echo ""
echo "Pressione Ctrl+C para parar ambos os servidores"
echo ""

# Aguardar interrupção
trap "echo ''; echo '🛑 Parando servidores...'; kill $BACKEND_PID $FRONTEND_PID; exit" INT

wait
