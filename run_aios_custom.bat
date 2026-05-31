@echo off
cd /d D:\aios\aios
echo ============================================
echo   AIOS Shell - Connected to Custom AI
echo ============================================
echo Provider : Custom (http://localhost:20128/v1)
echo Model    : code
echo ============================================
echo.
python -m shell.nl_shell --ai-provider custom --ai-model code --ai-key sk-576a1c43755b51a6-be3nal-aa9f6298 --ai-url http://localhost:20128/v1